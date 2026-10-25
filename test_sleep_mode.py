import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import _normalize_text, _is_sleep_command, _is_wake_command

class TestSleepMode(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(_normalize_text("Ramma, dorme!"), "ramma dorme")
        self.assertEqual(_normalize_text("  VAI   DORMIR... "), "vai dormir")
        self.assertEqual(_normalize_text("Ramma, tá aí?"), "ramma ta ai")

    def test_sleep_commands(self):
        # Should trigger sleep
        sleep_inputs = [
            "Ramma, dorme",
            "Ramma, vai dormir",
            "Ramma, pode dormir",
            "Ramma, para de me ouvir",
            "Ramma, não me escuta agora",
            "Dorme",
            "Vai dormir",
            "Silencio"
        ]
        for text in sleep_inputs:
            with self.subTest(text=text):
                self.assertTrue(_is_sleep_command(text), f"Expected sleep command for: {text}")

    def test_negative_sleep_commands(self):
        # Should NOT trigger sleep (false positives)
        non_sleep_inputs = [
            "Eu dormi mal ontem",
            "Dormi pouco esta noite",
            "Dormi tarde",
            "Ele dormiu no sofá",
            "Vou dormir",
            "Ela está dormindo",
            "Vou jogar agora",
            "Olha isso",
            "Vou entrar no Discord",
            "Diogo, espera"
        ]
        for text in non_sleep_inputs:
            with self.subTest(text=text):
                self.assertFalse(_is_sleep_command(text), f"Expected NOT sleep command for: {text}")

    def test_wake_commands(self):
        # Should trigger wake up
        wake_inputs = [
            "Ramma, acorda",
            "Ramma, tá aí",
            "Ramma, você tá aí",
            "Ei, Ramma",
            "Ramma, me escuta",
            "Acorda",
            "Tá aí",
            "Jarvis"
        ]
        for text in wake_inputs:
            with self.subTest(text=text):
                self.assertTrue(_is_wake_command(text), f"Expected wake command for: {text}")

    def test_negative_wake_commands(self):
        # Ordinary speech while sleeping should not be recognized as wake command
        non_wake_inputs = [
            "vou jogar agora",
            "olha isso",
            "vou entrar no Discord",
            "Diogo, espera",
            "estou com fome"
        ]
        for text in non_wake_inputs:
            with self.subTest(text=text):
                self.assertFalse(_is_wake_command(text), f"Expected NOT wake command for: {text}")

if __name__ == '__main__':
    unittest.main()
