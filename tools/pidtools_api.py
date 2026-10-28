"""Vstupní bod sidecaru pro PyInstaller (pidtools-api): freeze_support dřív než cokoli těžkého (podproces úlohy)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from pidtools.api.sidecar import main
    sys.exit(main())
