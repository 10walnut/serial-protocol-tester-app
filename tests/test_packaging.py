from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))


def declared_app_version() -> str:
    source = (APP_ROOT / "serial_console.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if match is None:
        raise AssertionError("APP_VERSION literal not found in app/serial_console.py")
    return match.group(1)


class PackagingMetadataTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for relative in (
            "pyproject.toml",
            "MANIFEST.in",
            "README.md",
            "LICENSE",
            "app/__init__.py",
            "app/__main__.py",
            "app/serial_console.py",
            "app/serial_ports.py",
            "app/virtual_ports_posix.py",
            "app/sample_protocol.json",
            "app/sample_protocol.en.json",
            "app/assets/serial-protocol-tester-logo.png",
            "start_serial_console.sh",
            ".github/workflows/cross-platform.yml",
        ):
            with self.subTest(path=relative):
                self.assertTrue((PROJECT_ROOT / relative).is_file(), relative)

    def test_package_version_matches_application_version(self) -> None:
        init_source = (APP_ROOT / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_source, re.MULTILINE)
        self.assertIsNotNone(match)
        if match is None:
            return
        self.assertEqual(match.group(1), declared_app_version())

    def test_pyproject_declares_runtime_dependencies_and_entry_point(self) -> None:
        text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for expected in (
            "pyserial>=3.5,<4",
            "PySide6-Essentials>=6.7,<7",
            'requires-python = ">=3.10"',
            "serial_protocol_assistant.serial_console:main",
            "serial-protocol-assistant",
            'build-backend = "setuptools.build_meta"',
            'license-files = ["LICENSE"]',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    @unittest.skipIf(tomllib is None, "tomllib requires Python 3.11+")
    def test_pyproject_metadata(self) -> None:
        self.assertIsNotNone(tomllib)
        if tomllib is None:
            return
        data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        build = data["build-system"]
        self.assertEqual(build["build-backend"], "setuptools.build_meta")
        self.assertTrue(any(item.startswith("setuptools>=") for item in build["requires"]))
        self.assertIn("wheel", build["requires"])

        project = data["project"]
        self.assertEqual(project["name"], "serial-protocol-assistant")
        self.assertEqual(project["version"], declared_app_version())
        self.assertEqual(project["requires-python"], ">=3.10")
        self.assertEqual(project["license"], "LicenseRef-PolyForm-Noncommercial-1.0.0")
        self.assertEqual(project["license-files"], ["LICENSE"])
        self.assertFalse(
            any("License :: OSI Approved" in item for item in project["classifiers"]),
            "PolyForm Noncommercial is not an OSI approved license",
        )
        self.assertEqual(
            set(project["dependencies"]),
            {
                line.strip()
                for line in (APP_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            },
        )
        self.assertEqual(
            project["scripts"]["serial-protocol-assistant"],
            "serial_protocol_assistant.serial_console:main",
        )
        self.assertEqual(
            project["gui-scripts"]["serial-protocol-assistant-gui"],
            "serial_protocol_assistant.serial_console:main",
        )

        setuptools = data["tool"]["setuptools"]
        self.assertIn("serial_protocol_assistant", setuptools["packages"])
        self.assertEqual(setuptools["package-dir"]["serial_protocol_assistant"], "app")
        self.assertFalse(setuptools["include-package-data"])
        package_data = setuptools["package-data"]["serial_protocol_assistant"]
        for pattern in (
            "sample_protocol.json",
            "sample_protocol.en.json",
            "assets/*.png",
            "assets/*.jpg",
            "assets/*.ico",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, package_data)

    def test_manifest_includes_license_and_sources(self) -> None:
        text = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for expected in (
            "README.md", "LICENSE", "tests", "scripts", "app/assets",
            "start_serial_console.sh", "build_serial_console.ps1",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_documentation_versions_match(self) -> None:
        version = declared_app_version()
        guide = (PROJECT_ROOT / "docs/user-guide/guide.json").read_text(encoding="utf-8")
        self.assertIn(f'"version": "{version}"', guide)
        for relative in (
            "docs/user-guide/README.md",
            "docs/user-guide/README.en.md",
        ):
            with self.subTest(path=relative):
                self.assertIn(
                    version,
                    (PROJECT_ROOT / relative).read_text(encoding="utf-8"),
                )

    def test_readme_documents_supported_commands(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        for expected in (
            "python -m pip install .",
            "serial-protocol-assistant --self-test",
            "python -m serial_protocol_assistant --self-test",
            "serial-protocol-assistant-gui",
            "bash start_serial_console.sh",
            "python -m build",
            "python -m pip check",
        ):
            with self.subTest(command=expected):
                self.assertIn(expected, readme)

    @unittest.skipIf(tomllib is None, "tomllib requires Python 3.11+")
    def test_build_extra_matches_windows_builder(self) -> None:
        if tomllib is None:
            self.fail("tomllib is required")
        data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = data["project"]["optional-dependencies"]["build"]
        builder = (PROJECT_ROOT / "build_serial_console.ps1").read_text(encoding="utf-8")
        for requirement in requirements:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, builder)

    def test_built_wheel_contains_package_data(self) -> None:
        import zipfile

        wheels = sorted((PROJECT_ROOT / "dist").glob("*.whl"))
        if not wheels:
            self.skipTest("no wheel built in this checkout")
        names = set(zipfile.ZipFile(wheels[-1]).namelist())
        for relative in (
            "serial_protocol_assistant/__init__.py",
            "serial_protocol_assistant/__main__.py",
            "serial_protocol_assistant/serial_ports.py",
            "serial_protocol_assistant/virtual_ports_posix.py",
            "serial_protocol_assistant/sample_protocol.json",
            "serial_protocol_assistant/sample_protocol.en.json",
        ):
            with self.subTest(path=relative):
                self.assertIn(relative, names)
        self.assertTrue(
            any(name.startswith("serial_protocol_assistant/assets/") for name in names),
            "assets must be packaged as package data",
        )
        self.assertNotIn(
            "serial_protocol_assistant/release-defaults.json",
            names,
            "pip builds must not pin a release language",
        )


if __name__ == "__main__":
    unittest.main()
