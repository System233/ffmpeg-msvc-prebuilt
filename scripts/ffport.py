#!/usr/bin/env python3
"""Entry point — delegates to the ffport package.

Usage:
  ffport generate 8.1.1
  ffport generate n8.1.1-50-gabc1234 --sha512 <hash>
  ffport generate --all
  ffport list
  ffport deps
"""

from ffport import main

main()
