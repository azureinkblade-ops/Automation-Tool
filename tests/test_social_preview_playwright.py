import tempfile
import subprocess
import unittest
from pathlib import Path

import app


class SocialPreviewPlaywrightTests(unittest.TestCase):
    def test_generated_helper_avoids_meta_business_tabs_and_verifies_x_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            script = app.write_manual_posts_playwright_script(
                folder,
                [
                    {"key": "x", "label": "X", "url": "https://x.com/compose/post", "text": "Test", "media_path": ""},
                    {"key": "facebook", "label": "Facebook", "url": "https://www.facebook.com/", "text": "Test", "media_path": ""},
                ],
            )
            source = script.read_text(encoding="utf-8")
            syntax = subprocess.run(
                [str(app.bundled_node_executable()), "--check", str(script)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        self.assertIn("if (key === 'facebook')", source)
        self.assertIn("composerVisible", source)
        self.assertIn("host === 'facebook.com' || host === 'm.facebook.com'", source)
        self.assertIn("return null;", source)
        self.assertIn('[data-testid="tweetPhoto"]', source)
        self.assertIn("selectedFiles", source)
        self.assertIn("verifiedAttached", source)
        self.assertIn("mediaRequired", source)
        self.assertNotIn("assumedAttached: true", source)


if __name__ == "__main__":
    unittest.main()
