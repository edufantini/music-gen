import sys
import numpy as np
import pandas as pd
from music21 import *
import glob
from tqdm import tqdm
import matplotlib.pyplot as plt
from scipy import interpolate

path = '../data/English_Man_In_New_York.1.mid'
N_FRAMES = 36
N_NOTES = 88
MIDI_OFFSET = 20


def int2note(i):
    index = i + MIDI_OFFSET
    n = note.Note(midi=index)
    return n


# open and read file
def open_midi(midi_path, no_drums):
    mf = midi.MidiFile()
    mf.open(midi_path)
    mf.read()
    mf.close()
    if (no_drums):
        for i in range(len(mf.tracks)):
            mf.tracks[i].events = [ev for ev in mf.tracks[i].events if ev.channel != 10]

    return midi.translate.midiFileToStream(mf)


# get all notes from m21 obj
def extract_notes(midi):
    parent_element = []
    # print(midi_part)
    # ret = []
    for nt in midi.flat.notes:
        if isinstance(nt, note.Note):
            parent_element.append(nt)
        elif isinstance(nt, chord.Chord):
            for p in nt.pitches:
                # print(p, note.Note(pitch=p))
                # input()
                parent_element.append(note.Note(pitch=p))

    # print(parent_element)
    # input()
    return parent_element


# extract frames from each measure
def measure2frames(measure, n_frames, ks, bpm, ts):
    measure_notes = extract_notes(measure)

    frame_s = None
    frame_e = None

    frames_beat = n_frames / ts.numerator

    frames = [[0 for a in range(N_NOTES)] for b in range(n_frames)]

    for nt in measure_notes:

        if nt.pitch.midi > N_NOTES + MIDI_OFFSET:
            break

        # try:
        # print(nt.offset)
        frame_s = int(nt.offset * frames_beat)
        # except:
        # print('a')
        # break
        # pass

        # try:
        # print(int(nt.quarterLength * frames_beat))
        frame_e = frame_s + int(nt.quarterLength * frames_beat)
        # except:
        # print('b')
        # break
        # pass

        index = nt.pitch.midi - MIDI_OFFSET

        for i in range(frame_s, frame_e):
            # frames[i][index] = index
            frames[i][index] = 1

        # print('{} | Índice: {} | Frame início: {} \t| \t Frame final: {}'.format(nt.nameWithOctave, index, frame_s, frame_e))
        # input()

    output = [ks.tonicPitchNameWithCase,
              bpm,
              '{}/{}'.format(ts.numerator, ts.denominator),
              frames]
    print(output)

    # print('\n', pd.DataFrame(output).to_string())
    # input()
    return output


# encode the file data from a .mid file
def encode_data(path, n_frames):
    print('Processing file {}'.format(path))
    score = open_midi(path, True)

    # transpose song to C major/A minor
    ks = score.analyze('key')
    if ks != 'C' and ks != 'a':
        if ks.mode == 'major':
            transpose_int = interval. \
                Interval(ks.tonic, pitch.Pitch('C'))
            score = score.transpose(transpose_int)
            ks = key.Key('C')
        elif ks.mode == 'minor':
            transpose_int = interval. \
                Interval(ks.tonic, pitch.Pitch('a'))
            score = score.transpose(transpose_int)
            ks = key.Key('a')

    n = len(score.parts)
    parts = []

    for i, part in enumerate(score.parts):

        print('Processing part {}/{}'.format(i + 1, n))

        # get part instrument
        inst = part.getElementsByClass(instrument.Instrument)[0].instrumentName
        print(inst)
        # input()

        # get part tempo
        metronome = part.getElementsByClass(tempo.TempoIndication)[0]
        bpm = metronome.getQuarterBPM()

        # filter parts that are not in 4/4
        ts = part.getTimeSignatures()[0]
        if ts.numerator != 4 and ts.denominator != 4:
            print('Part not 4/4')
            return

        part_frames = []
        for it in tqdm(part.measures(0, len(part)),
                       desc="Converting part {}".format(i + 1),
                       ncols=80):

            # check for tempo changes
            try:
                m_bpm = it.getElementsByClass(tempo.TempoIndication)[0].getQuarterBPM()
                if m_bpm is not None and m_bpm != bpm:
                    bpm = m_bpm
            except:
                pass

            # check for time sign changes
            m_ts = score.getTimeSignatures()[0]
            if m_ts is not None and m_ts != ts:
                # it changed
                if ts.numerator != 4 and ts.denominator != 4:
                    print('Measure not 4/4')
                    break
                else:
                    ts = m_ts

            if isinstance(it, stream.Stream):
                part_frames.append(measure2frames(it, n_frames, ks, bpm, ts))

        this_part = [inst,
                     ks.tonicPitchNameWithCase,
                     bpm,
                     '{}/{}'.format(ts.numerator, ts.denominator),
                     np.asarray(part_frames)]
        # print(this_part[0:4])
        # input()
        # print(this_part[4:])
        # input()
        parts.append(this_part)

    np.save(arr=parts, file='teste')

    return parts


# decode a N_NOTESxN_FRAMES array and turn it into a m21 Measure
def decode_measure(measure, n_frames, ts):
    last_frame = False

    # the stream that will receive the notes
    output = stream.Measure()

    # vectors that will hold the current notes states and durations
    # they are initialized with the values of the first frame
    state_register = measure[:][0].copy().to_numpy()
    start_register = measure[:][0].copy().to_numpy() - 1
    duration_register = measure[:][0].copy().to_numpy()

    # iterate over frames
    for f in range(n_frames):
        # print('Frame ', f)
        # with np.printoptions(threshold=np.inf):
        #     print('\nStates:\t', state_register.reshape(1, 88))
        #     print('\nStarts:\t', start_register.reshape(1, 88))
        #     print('\nDurs:\t', duration_register.reshape(1, 88))
        # input()

        frames_per_beat = n_frames / ts.numerator

        frame = measure[f]

        if f == n_frames - 1:
            last_frame = True

        # print("Frame {}\n".format(f), frame)
        # input()

        # iterate over notes
        # state is ON/OFF 1/0
        for note_index, state in enumerate(frame):

            # if note state changed
            if bool(state) != bool(state_register[note_index]):

                # 1 -> *0*
                if bool(state) is False:

                    nt = int2note(note_index)
                    nt.duration.quarterLength = duration_register[note_index] / frames_per_beat

                    note_offset = start_register[note_index] / frames_per_beat
                    output.insert(note_offset, nt)

                    # print('Note {} turned off at frame {}\n'.format(int2note(note_index).nameWithOctave, f + 1) +
                    #       'offset of {} frames ({})\n'.format(start_register[note_index], note_offset) +
                    #       'and duration on {} frames ({})'.format(duration_register[note_index],
                    #                                               nt.duration.quarterLength))
                    # input()

                    # restarting the registers
                    duration_register[note_index] = 0
                    state_register[note_index] = 0
                    start_register[note_index] = -1


                # 0 -> *1*
                else:
                    # starting registers
                    duration_register[note_index] = 1
                    state_register[note_index] = 1
                    start_register[note_index] = f

                    # print('Note {} turned on at frame {}'.format(int2note(note_index).nameWithOctave, f + 1))
                    # input()

            # if note is on and didnt change, increase duration
            elif bool(state) is True:
                duration_register[note_index] += 1

                # print('Note {} increased duration at frame {} ({} frames)'.
                #       format(int2note(note_index).nameWithOctave, f + 1, duration_register[note_index]))
                # input()

            # note is ON and measure ended
            elif bool(state_register[note_index]) and last_frame:

                nt = int2note(note_index)
                note.duration.quarterLength = duration_register[note_index] / frames_per_beat

                note_offset = start_register[note_index] / frames_per_beat
                output.insert(note_offset, nt)
                # print('Note {} turned off at frame {}\n'.format(int2note(note_index).nameWithOctave, f + 1) +
                #       'offset of {} frames ({})\n'.format(start_register[note_index], note_offset) +
                #       'and duration on {} frames ({})'.format(duration_register[note_index], nt.duration.quarterLength))
                # input()

    return output


# decode a PARTxN_NOTESxN_FRAMES array
def decode_part(part, n_frames):
    decoded = stream.Stream()

    # part settings
    try: decoded.append(instrument.fromString(part[0]))
    except: pass
    decoded.append(key.Key(part[1]))
    decoded.append(tempo.MetronomeMark(number=part[2], referent='quarter'))
    ts = meter.TimeSignature(part[3])
    decoded.append(ts)

    part_measures = part[4:][0]

    # iterate over measures (bars)
    for i, m in enumerate(part_measures):

        # measure settings
        decoded.append(key.Key(m[0]))
        decoded.append(tempo.MetronomeMark(number=m[1], referent='quarter'))
        # decoded.append(tempo.TempoIndication(m[1]))
        decoded.append(meter.TimeSignature(m[2]))

        # now here comes the frames
        measure = pd.DataFrame(m[3:][0])
        measure = measure.T
        # print("Measure {}\n".format(i+1), measure)
        # input()
        decoded.append(decode_measure(measure, n_frames, meter.TimeSignature('4/4')))

    decoded.write('midi', fp='decoded.mid')
    print('Saved')
    input()


# get encoded file parts with N_FRAMES frames per measure (bar)
parts = encode_data(path, N_FRAMES)

for i, part in enumerate(parts):
    # print(part.shape)
    print('Part #{}'.format(i + 1))
    decode_part(part, N_FRAMES)
