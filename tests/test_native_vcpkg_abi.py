"""Native vcpkg ABI migration regression; offline except the optional smoke."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.identity import variant_name
from ffbuild.native_abi import (build_requests, read_nuget_abis, scan_native_abis,
                               verify_job_abi)
from ffbuild.package import _verify_native_package_abi, package_job
from ffbuild.planner import plan_native
from ffbuild.port import ffmpeg_port_name, generate_port
from ffbuild.state import PublishedState
from ffbuild.catalog import register_release
from ffbuild.targets import Target
from ffbuild.versions import ROOT, generate_all, has_source, versions


class NativeABIQueries(unittest.TestCase):
    def test_nuget_native_abi_exactly_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "packages.config"
            path.write_text('<?xml version="1.0"?><packages><package '
                            'id="ffmpeg_x64-windows" '
                            'version="8.1.3-vcpkg' + 'a' * 64 + '" /></packages>',
                            encoding="utf-8")
            self.assertEqual({'ffmpeg_x64-windows': 'a' * 64},
                             read_nuget_abis(path))
            path.write_text('<packages><package id="ffmpeg_x64-windows" '
                            'version="8.1.3" /></packages>', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
                read_nuget_abis(path)

    def test_two_versions_are_scanned_in_isolated_dependency_graphs(self):
        targets = (Target('ffmpeg[base,static]', 'x64-windows', ('base', 'static')),
                   Target('ffmpeg[all-lgpl]', 'x64-windows', ('all-lgpl',)))
        items = []
        for release in ('8.1.3', '9.1'):
            req, errors = build_requests(version=release, targets=targets)
            self.assertFalse(errors)
            items.extend(req)
        queries = []

        def native(specs, triplet, **kwargs):
            queries.append((tuple(specs), triplet, kwargs['port_overlay'].name))
            self.assertEqual(2, len(specs))
            self.assertEqual("ffmpeg-tester", specs[1])
            return {f"{spec.split('[', 1)[0]}_{triplet}":
                    str(len(queries)) * 64 for spec in specs}

        with mock.patch('ffbuild.native_abi.native_abi_query', side_effect=native):
            results = scan_native_abis(items)
        self.assertEqual(4, len(results))
        self.assertEqual(4, len(queries))
        self.assertEqual(4, len({item['id'] for item in results}))
        self.assertEqual(4, len({item['native_graph_sha256'] for item in results}))
        self.assertEqual({'ffmpeg'}, {item['port'] for item in results})
        self.assertEqual({'ffmpeg-tester'}, {item['tester_port'] for item in results})
        self.assertEqual({'ffmpeg-8-1-3', 'ffmpeg-9-1'}, {entry[2] for entry in queries})

    def test_native_query_must_select_one_direct_stable_ffmpeg_port(self):
        from types import SimpleNamespace
        from ffbuild.native_abi import native_abi_query
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = root / 'ffmpeg-9-1'
            port.mkdir()
            (port / 'vcpkg.json').write_text('{"name":"ffmpeg","version":"9.1"}')
            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                self.assertEqual(1, args.count('--x-abi-tools-use-exact-versions'))
                self.assertEqual('1', kwargs['env']['VCPKG_FORCE_DOWNLOADED_BINARIES'])
                output_arg = next(arg for arg in args if arg.startswith(
                    '--x-write-nuget-packages-config='))
                output = Path(output_arg.split('=', 1)[1])
                output.write_text('<packages><package id="ffmpeg_x64-windows" '
                                  'version="9.1-vcpkg' + 'a' * 64 + '" /></packages>')
                return SimpleNamespace(returncode=0, stdout='', stderr='')

            with mock.patch('ffbuild.native_abi.subprocess.run', side_effect=fake_run):
                self.assertEqual('a' * 64, native_abi_query(
                    ['ffmpeg[base]'], 'x64-windows', port_overlay=port,
                    binary=Path(__file__))['ffmpeg_x64-windows'])
            self.assertEqual(1, len(calls))
            args = calls[0]
            self.assertIn(f'--overlay-ports={port.resolve()}', args)
            self.assertNotIn(f'--overlay-ports={root.resolve()}', args)
            self.assertIn('ffmpeg[base]', args)
            (port / 'vcpkg.json').write_text('{"name":"ffmpeg-9-1","version":"9.1"}')
            with self.assertRaisesRegex(ValueError, 'stable ffmpeg'):
                native_abi_query(['ffmpeg[base]'], 'x64-windows',
                                 port_overlay=port, binary=Path(__file__))
            with self.assertRaisesRegex(FileNotFoundError, 'Select a generated'):
                native_abi_query(['ffmpeg[base]'], 'x64-windows',
                                 port_overlay=root, binary=Path(__file__))

    def test_preflight_rejects_abi_drift(self):
        job = {'yaml': '8.1.3', 'port': 'ffmpeg', 'package': 'ffmpeg[base]',
               'triplet': 'x64-windows', 'abi_hash': 'a' * 64,
               'tester_port': 'ffmpeg-tester', 'native_graph_sha256': 'c'*64}
        with mock.patch('ffbuild.native_abi.native_abi_query', return_value={
                'ffmpeg_x64-windows': 'b' * 64}):
            with self.assertRaisesRegex(ValueError, "ABI changed"):
                verify_job_abi(job)


    def test_preflight_rejects_tester_only_abi_drift(self):
        from ffbuild.native_abi import graph_digest
        planned = {"ffmpeg_x64-windows": "a"*64, "ffmpeg-tester_x64-windows": "b"*64}
        job = {"yaml": "8.1.3", "port": "ffmpeg", "tester_port": "ffmpeg-tester",
               "package": "ffmpeg[base]", "triplet": "x64-windows", "abi_hash": "a"*64,
               "native_graph_sha256": graph_digest(planned)}
        with mock.patch("ffbuild.native_abi.native_abi_query", return_value=planned):
            self.assertEqual("a"*64, verify_job_abi(job))
        with mock.patch("ffbuild.native_abi.native_abi_query",
                        return_value=dict(planned, **{"ffmpeg-tester_x64-windows": "c"*64})):
            with self.assertRaisesRegex(ValueError, "ABI graph changed"):
                verify_job_abi(job)


class VersionedPorts(unittest.TestCase):
    def test_msvc_host_tool_paths_and_pkgconfig_are_generated(self):
        """The generated recipe must actually find tools during real builds."""
        with tempfile.TemporaryDirectory() as tmp:
            port = generate_port('8.1.3', destination=Path(tmp))
            wrapper = (port / 'portfile.cmake').read_text(encoding='utf-8')
            recipe = (port / 'builder/ffmpeg-portfile.cmake').read_text(encoding='utf-8')
            self.assertIn('builder/ffmpeg-portfile.cmake', wrapper)
            self.assertIn('list(APPEND prog_env "${MSYS_ROOT}/usr/bin"', recipe)
            self.assertIn('vcpkg_add_to_path(PREPEND ${prog_env})', recipe)
            self.assertIn('vcpkg_find_acquire_program(NASM)', recipe)
            self.assertIn('vcpkg_find_acquire_program(GASPREPROCESSOR)', recipe)
            self.assertIn('vcpkg_find_acquire_program(PKGCONFIG)', recipe)
            self.assertIn('ffmpeg_setup_native_pkgconfig(RELEASE)', recipe)
            self.assertIn('ffmpeg_setup_native_pkgconfig(DEBUG)', recipe)
            self.assertIn('z_vcpkg_setup_pkgconfig_path(CONFIG ${_config})', recipe)
            self.assertIn('z_vcpkg_restore_pkgconfig_path()', recipe)
            self.assertIn('manual-tools/ffmpeg-bin2c', recipe)
            self.assertIn('manual-tools/ffmpeg-opstool', recipe)
            self.assertIn('vcpkg_copy_tools(', recipe)
            self.assertIn('vcpkg_fixup_pkgconfig()', recipe)
            self.assertIn('vcpkg_host_path_list(PREPEND ENV{LIB}', recipe)
            self.assertIn('--extra-ldflags=-L', recipe)
            self.assertIn('"${CURRENT_PACKAGES_DIR}/debug/include"', recipe)

    def test_generator_compiles_all_source_backed_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ports = generate_all(output=directory)
            self.assertEqual(sum(has_source(name) for name in versions()), len(ports))
            self.assertEqual(len(ports), len({port.name for port in ports}))
            for port in ports:
                manifest = json.loads((port / 'vcpkg.json').read_text())
                self.assertEqual('ffmpeg', manifest['name'])
                self.assertEqual('ffmpeg-tester', json.loads(
                    (ROOT / 'ports/ffmpeg-tester/vcpkg.json').read_text())['name'])
                self.assertFalse((directory / port.name.replace('ffmpeg-', 'ffmpeg-tester-', 1)).exists())
                self.assertFalse(any('ffmpeg-' in str(dep)
                                     for part in manifest['features'].values()
                                     for dep in part.get('dependencies', [])))

    def test_master_source_pinned_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = generate_port('master', destination=Path(tmp),
                                 source_version='n9.1-12-gabcdef0', ref='a' * 40,
                                 sha512='b' * 128)
            self.assertEqual('ffmpeg-master', port.name)
            self.assertEqual('ffmpeg', json.loads(
                (port / 'vcpkg.json').read_text())['name'])
            self.assertIn('a' * 40, (port / 'portfile.cmake').read_text())
            self.assertFalse((port.parent / 'ffmpeg-tester-master').exists())

    def test_version_names_reject_malformed_input(self):
        self.assertEqual('ffmpeg-8-1-3', ffmpeg_port_name('8.1.3'))
        for name in ('../8.1.3', '8.1.3-test', '8.1.3/../../', 'a'):
            with self.assertRaises(ValueError):
                ffmpeg_port_name(name)


class NativePublication(unittest.TestCase):
    def test_real_vcpkg_abi_inputs_are_required_at_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            native = 'f' * 64
            with self.assertRaisesRegex(FileNotFoundError, "ABI inputs missing"):
                _verify_native_package_abi(package, 'ffmpeg-8-1-3', native)
            metadata = package / 'share' / 'ffmpeg' / 'vcpkg_abi_info.txt'
            metadata.parent.mkdir(parents=True)
            metadata.write_text('the actual ABI inputs', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, "differs from planned"):
                _verify_native_package_abi(package, 'ffmpeg', native)
            import hashlib
            actual = hashlib.sha256(metadata.read_bytes()).hexdigest()
            _verify_native_package_abi(package, 'ffmpeg', actual)

    def test_packaging_and_data_dedup_use_only_native_abi(self):
        requests, blocked = build_requests(
            version='8.1.3',
            targets=(Target('ffmpeg[base]', 'x64-windows', ('base',)),))
        self.assertFalse(blocked)
        job = requests[0]
        abi = 'a' * 64
        job['abi_hash'] = abi
        job['id'] = variant_name(job['version'], 0, job['triplet'],
                                 job['linkage'], job['license'], abi_hash=abi)
        scan = {'schema': 3, 'jobs': [job]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'package'
            (package / 'bin').mkdir(parents=True)
            (package / 'lib').mkdir()
            (package / 'include').mkdir()
            copyright = package / 'share' / job['port'] / 'copyright'
            copyright.parent.mkdir(parents=True)
            copyright.write_text(
                'GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n',
                encoding='utf-8')
            (copyright.parent / 'vcpkg_abi_info.txt').write_text(
                'native ABI inputs for this simulated built package', encoding='utf-8')
            import hashlib
            actual_abi = hashlib.sha256(
                (copyright.parent / 'vcpkg_abi_info.txt').read_bytes()).hexdigest()
            job['abi_hash'] = actual_abi
            job['id'] = variant_name(job['version'], 0, job['triplet'],
                                     job['linkage'], job['license'], abi_hash=actual_abi)
            (package / 'bin' / 'ffmpeg.exe').write_bytes(b'program')
            (package / 'lib' / 'avcodec.lib').write_bytes(b'library')
            (package / 'include' / 'avcodec.h').write_bytes(b'header')
            (package / 'CONTROL').write_text(
                f"Package: {job['port']}\nVersion: {job['version']}\n"
                f"Port-Version: {0}\n\n" +
                '\n\n'.join('Feature: ' + f for f in job['features'] + ['core']),
                encoding='utf-8')
            (package / 'BUILD_INFO').write_text('LibraryLinkage: dynamic\n',
                                                 encoding='utf-8')
            from compliance_fixture import make_compliance_fixture
            installed, source_tree = make_compliance_fixture(root, job, copyright)
            metadata = package_job(
                package, job, root / 'assets',
                installed_root=installed, source_tree=source_tree)
            record = yaml.safe_load(metadata.read_text(encoding='utf-8'))
            self.assertEqual(actual_abi, record['abi_hash'])
            self.assertNotIn('build_hash', record)
            self.assertNotIn('feature_hash', record)
            self.assertEqual(1, len(plan_native(scan, state=PublishedState(
                directory=root / 'data'))['jobs']))
            data_path = register_release(root / 'data', [dict(record, expected_variants=1)])
            self.assertEqual(record["version"] + ".json", data_path.name)
            self.assertNotIn("revision", record)
            self.assertTrue(record["assets"]["binary"]["file"].endswith(
                "-" + job["release_date"][2:].replace("-", "") + ".zip"))
            self.assertEqual([], plan_native(scan, state=PublishedState(
                directory=root / 'data'))['jobs'])


if __name__ == '__main__':
    unittest.main()
