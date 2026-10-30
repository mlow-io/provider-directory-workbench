"""Compatibility entry point for the shared synthetic fixture contract."""
from pathlib import Path
from provider_directory_truth_layer.demo_samples import generate

if __name__ == '__main__':
    import sys
    print(generate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.runtime/demo-inputs')))
