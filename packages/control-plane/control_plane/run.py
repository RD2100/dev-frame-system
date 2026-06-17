"Entry point for control_plane.run module."
from .pipeline_runner import run_cli
import sys

if __name__ == "__main__":
    sys.exit(run_cli())
