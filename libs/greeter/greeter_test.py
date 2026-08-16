import unittest

from libs.greeter import greeter


class GreetTest(unittest.TestCase):
    def test_greets_the_given_name(self):
        self.assertEqual(greeter.greet("vikrant"), "hello, vikrant!")

    def test_falls_back_to_default_name(self):
        self.assertEqual(greeter.greet(None), "hello, world!")
        self.assertEqual(greeter.greet("   "), "hello, world!")

    def test_build_info_carries_the_generated_version(self):
        info = greeter.build_info("api", environment="ci")
        self.assertEqual(info["service"], "api")
        self.assertEqual(info["environment"], "ci")
        # The version comes from //release:version.txt via the genrule, so this
        # assertion also proves the codegen edge of the build graph works.
        self.assertRegex(info["version"], r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
