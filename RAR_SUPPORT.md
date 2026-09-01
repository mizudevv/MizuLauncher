# RAR support

MizuLauncher supports ZIP and RAR. RAR extraction uses the open-source 7-Zip command-line tool. On first RAR extraction, if 7-Zip is not already installed, the launcher downloads the official 7-Zip 26.02 Extra package, verifies its SHA-256, extracts `7zz.exe` with py7zr, caches it under `%LOCALAPPDATA%\MizuLauncher\tools`, and uses it for RAR extraction.

Official 7-Zip: https://www.7-zip.org/download.html
