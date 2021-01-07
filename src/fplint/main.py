""" Entry point to the linting script

This is the main entry point to the fplint script.
"""
import argparse
import os
import glob
from pathlib import Path
import sys

from fprime.fbuild.settings import IniSettings
# Weeping sadness: fprime_ac is not available as a package, so setting must be loaded globally and python path adjusted
#                  before anu fprime_ac modules are loaded. The BUILD_ROOT options then need to be patched such that the
#                  fprime_ac modules work as expected.
try:
    SETTINGS = IniSettings.load(None, cwd=Path.cwd())
    sys.path.append(os.path.join(SETTINGS.get("framework_path"), "Autocoders", "src"))

    base_locations = [SETTINGS.get("framework_path"), SETTINGS.get("project_root", None)]
    base_locations.extend(SETTINGS.get("library_locations"))

    # AC Constants
    ac_consts = SETTINGS.get("ac_constants", None)
    if ac_consts:
        os.environ["FPRIME_AC_CONSTANTS_FILE"] = ac_consts

    # Old code uses BUILD_ROOT variable, so we should generate it from settings.ini
    from fprime_ac.utils.buildroot import set_build_roots
    set_build_roots(":".join([str(location) for location in base_locations if location is not None]))
except Exception as exc:
    print("[ERROR] Failure to load settings.ini and fprime_ac modules therein", exc, file=sys.stderr)
    sys.exit(1)

from fplint.load import load_configuration, load_model, LoadException
from fplint.checks.check import BaseCheck


def main():
    """ Entry point to the fplinter code"""
    parser = argparse.ArgumentParser(description="A linting module for F´ topologies")
    parser.add_argument("--config", type=argparse.FileType("r"),
                        help="Configuration YAML file to read linting configuration. Default: fplint.yml, if available")
    parser.add_argument("models", nargs="*",
                        help="Topology model to run linting against. **/*TopologyAppAi.xml")
    for key, vals in BaseCheck.get_all_extra_args().items():
        parser.add_argument("--"+key, **vals)
    arguments = parser.parse_args()

    # Defailt config if possible
    if arguments.config is None and Path("fplint.yml").exists():
        arguments.config = open(Path("fplint.yml"), "r")
    # Search for Topology
    if not arguments.models:
        globs = glob.glob("**/*TopologyAppAi.xml", recursive=True)
        if not globs:
            print("[ERROR] Could not find *TopologyAppAi.xml under current directory", file=sys.stderr)
            sys.exit(1)
        arguments.models = list(globs)
    try:
        # Note: load config after all imports have been done
        config = load_configuration(arguments.config, list(BaseCheck.get_all_identifiers([])))
        models = [load_model(model) for model in arguments.models]
    except LoadException as exc:
        print("[ERROR] {}".format(exc), file=sys.stderr)
        sys.exit(1)
    success = True
    for model in models:
        success = success and BaseCheck.run_all(model, excluded=config.get("exclusions", []), filters=config.get("filters", []), arguments=arguments)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()