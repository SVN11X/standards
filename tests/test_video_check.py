"""A finished video is checked from the file itself: streams, length, silent sound, soft subtitles and frames."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import media  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is not installed")
class VideoCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def make(self, name, audio, subtitles=False):
        out = self.dir / name
        args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=2",
                "-f", "lavfi", "-i", audio]
        if subtitles:
            srt = self.dir / "c.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,500\nHola\n", encoding="utf-8")
            args += ["-i", str(srt), "-map", "0", "-map", "1", "-map", "2", "-c:s", "mov_text"]
        subprocess.run([*args, "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out)], check=True)
        return out

    def test_sound_subtitles_and_frames_are_read_from_the_file(self):
        report = media.video_check(self.make("ok.mp4", "sine=frequency=440:duration=2", subtitles=True), self.dir / "f", 2)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual((report["video"], report["audio"], report["soft_subtitles"]), (1, 1, 1))
        self.assertEqual(len(report["frames"]), 2)
        self.assertTrue(all(Path(f).exists() for f in report["frames"]))

    def test_a_silent_track_is_a_problem(self):
        report = media.video_check(self.make("mute.mp4", "anullsrc=r=48000:cl=mono"))
        self.assertFalse(report["ok"])
        self.assertIn("the sound track is silent", report["problems"])


if __name__ == "__main__":
    unittest.main()
