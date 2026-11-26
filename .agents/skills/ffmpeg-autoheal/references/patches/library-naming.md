# Library Naming / Export Fixes

## Patches

| Patch | Versions | File | What it fixes |
|-------|----------|------|--------------|
| `create-lib-libraries` (various names) | 3.x, 4.x, 5.x (`0001-create-lib-libraries`), 6.x, 7.x, 8.x | `configure` | Sets `LIBPREF=""` and `LIBSUF=".lib"` for MSVC so it produces `.lib` static libraries instead of `.a` archives. Also comments out the `disable static` line to allow simultaneous shared+static builds. |

Specific filenames per version:

| Version directory | Patch filename |
|-------------------|---------------|
| 3.x | `create-lib-libraries.patch` |
| 4.x | `0001-create-lib-libraries.patch` |
| 5.x | `0001-create-lib-libraries.patch` |
| 6.x | `0001-create-lib-libraries-6.0.patch`, `0001-create-lib-libraries-6.1.patch` |
| 7.x | `0001-create-lib-libraries-6.1.patch` (reuses 6.1 patch) |
| 8.x | `0001-create-lib-libraries-6.1.patch` (reuses 6.1 patch) |

## When to check this category

- MSVC produces `.a` files instead of `.lib`
- Linker can't find `.lib` import libraries
- Static build with shared linkage produces wrong file extensions
