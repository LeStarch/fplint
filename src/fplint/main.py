""" Entry point to the linting script

This is the main entry point to the fplint script.
"""
import argparse
import glob
from pathlib import Path
import sys

from fplint.config import load_configuration, ConfigurationException
from fplint.model.patcher import load_patched_topology, InconsistencyException
from fplint.check import CheckBase
import fplint.checks

def main():
    """ Entry point to the fplint code"""
    parser = argparse.ArgumentParser(description="A linting module for F´ topologies")
    parser.add_argument("--config", type=argparse.FileType("r"),
                        help="Configuration YAML file to read linting configuration. Default: fplint.yml, if available")
    parser.add_argument("model", nargs='?', help="Topology model to run linting against. **/*TopologyAppAi.xml")

    # Allow checks to require additional inputs.
    # TODO: is this the best way to handel needing extra inputs
    for key, vals in CheckBase.get_all_extra_args().items():
        parser.add_argument("--"+key, **vals)
    arguments = parser.parse_args()

    # Load defailt fplint.yml file of ./fplint.yml
    if arguments.config is None and Path("fplint.yml").exists():
        arguments.config = open(Path("fplint.yml"), "r")

    # Attempt to find a topology model to verify if not specified by looking for matching children files
    if not arguments.model:
        globs = glob.glob("**/*TopologyAppAi.xml", recursive=True)
        if len(globs) != 1:
            print("[ERROR] Found {} toplogies matching **/*TopologyAppAi.xml in current working directory"
                  .format("no" if not globs else "too many"), file=sys.stderr)
            sys.exit(1)
        arguments.model = globs[0]

    # Loads configuration and check that configuration matches available code
    try:
        # Note: load config after all imports have been done
        config = load_configuration(arguments.config, list(CheckBase.get_all_identifiers([])))
    except ConfigurationException as exc:
        print("[ERROR] {}".format(exc), file=sys.stderr)
        sys.exit(1)

    # Try to load the model and  report errors if it fails to load a consistent model
    # TODO: XML linting checks should clear up any errors here.  Can we get them to run first, before loading models?
    try:
        topology_model = load_patched_topology(Path(arguments.model))
    except InconsistencyException as inc:
        print("[ERROR] Loading model detected specification error {}".format(inc), file=sys.stderr)
        sys.exit(1)

    # Run all topology model checking
    success = CheckBase.run_all(topology_model, excluded=config.get("exclusions", []),
                                filters=config.get("filters", []), arguments=arguments)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()