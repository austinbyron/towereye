import cv2
import numpy as np

from towereye.frames import VideoFileSource


def _write_video(path, n_frames=10, size=(64, 48)):
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, size)
    for i in range(n_frames):
        frame = np.full((size[1], size[0], 3), i * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_video_file_source_yields_all_frames(tmp_path):
    video = tmp_path / "clip.mp4"
    _write_video(video, n_frames=10)
    frames = list(VideoFileSource(video).frames())
    assert len(frames) == 10
    assert frames[0].shape == (48, 64, 3)
    assert frames[0].dtype == np.uint8
