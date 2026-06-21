# CLI tool reference

All commands run from repo root unless specified.

## Port generation

| Command | Purpose |
|---------|---------|
| `python scripts/ffport.py generate 8.1.1` | Generate vcpkg port from YAML chain |
| `python scripts/ffport.py generate master --version n8.2-50-gabc1234 --sha512 <128hex>` | Generate master branch port |
| `python scripts/ffport.py generate 8.1.1 -o C:\tmp\test_port` | Generate to custom dir for inspection |
| `python scripts/ffport.py list` | List all available version YAMLs |
| `python scripts/ffport.py deps` | Generate ffmpeg-deps virtual port |
| `python scripts/ffport.py get-revision 8.1.1` | Print revision from YAML chain |

## Version discovery

| Command | Purpose |
|---------|---------|
| `python scripts/find_closest_yaml.py --version 6.5` | Find closest existing YAML for a new version |

## Naming and parsing

| Command | Purpose |
|---------|---------|
| `python scripts/ops/naming.py variant-id --version 8.1.1 --revision 2 --triplet x64-windows --linkage shared --license gpl` | Build variant ID string |
| `python scripts/ops/naming.py release-tag --version 8.1.1 --revision 2` | Build release tag |
| `python scripts/ops/naming.py zip-name --variant-id "ffmpeg-8.1.1-r2_x64-windows-shared-gpl"` | Build ZIP filename |
| `python scripts/ops/naming.py parse --variant-id "ffmpeg-8.1.1-r2_x64-windows-shared-gpl"` | Parse variant ID into components |

## Detection

| Command | Purpose |
|---------|---------|
| `python scripts/ops/ci_detect_changes.py --base SHA --head SHA --json` | Detect which YAML versions changed between git refs |

## Validation

| Command | Purpose |
|---------|---------|
| `python -m pytest tests/ -v` | Run all unit tests |
| `python -m pytest tests/test_merge.py -v` | Run specific test file |
| `python -m pytest tests/test_features.py -v` | Test feature resolution |

## Log analysis

| Command | Purpose |
|---------|---------|
| `unzip -p log.zip ffmpeg/stdout-{triplet}.log \| grep -i "patch failed\|error:" \| tail -30` | Quick failure location |
| `unzip -p log.zip ffmpeg/build-{triplet}-rel-out.log \| tail -100 \| grep -i "error\|fatal\|LNK"` | Build output error scan |
