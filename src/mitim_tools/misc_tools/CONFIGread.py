import os
import sys
import json
import socket
import warnings
import logging
import getpass
from contextlib import contextmanager
from mitim_tools.misc_tools import IOtools
from IPython import embed


def load_settings(filename=None):
    if filename is None:
        filename = os.path.expanduser(
            os.path.expandvars("$MITIM_PATH/config/config_user.json")
        )

    # Load JSON
    with open(filename, "r") as f:
        settings = json.load(f)

    return settings


def read_verbose_level():
    s = load_settings()
    if "verbose_level" in s["preferences"]:
        verbose = int(s["preferences"]["verbose_level"])
    else:
        verbose = 1

    # Ignore warnings automatically if low level of verbose
    if verbose in [1, 2]:
        ignoreWarnings()

    return verbose


def read_dpi():
    s = load_settings()
    if "dpi_notebook" in s["preferences"]:
        dpi = int(s["preferences"]["dpi_notebook"])
    else:
        dpi = 100

    return dpi


def ignoreWarnings(module=None):
    if module is None:
        warnings.filterwarnings("ignore")
        logging.getLogger().setLevel(logging.CRITICAL)
    else:
        warnings.filterwarnings("ignore", module=module)  # "matplotlib\..*" )


class redirect_all_output_to_file:
    def __init__(self, logfile_path):
        self.logfile_path = logfile_path
        self.stdout_fd = None
        self.stderr_fd = None
        self.saved_stdout_fd = None
        self.saved_stderr_fd = None
        self.logfile = None

    def __enter__(self):
        # Save the actual stdout and stderr file descriptors.
        self.stdout_fd = sys.__stdout__.fileno()
        self.stderr_fd = sys.__stderr__.fileno()

        # Save a copy of the original file descriptors.
        self.saved_stdout_fd = os.dup(self.stdout_fd)
        self.saved_stderr_fd = os.dup(self.stderr_fd)

        # Open the log file.
        self.logfile = open(self.logfile_path, 'w')

        # Redirect stdout and stderr to the log file.
        os.dup2(self.logfile.fileno(), self.stdout_fd)
        os.dup2(self.logfile.fileno(), self.stderr_fd)

    def __exit__(self, exc_type, exc_value, traceback):
        # Restore stdout and stderr from the saved file descriptors.
        os.dup2(self.saved_stdout_fd, self.stdout_fd)
        os.dup2(self.saved_stderr_fd, self.stderr_fd)

        # Close the duplicated file descriptors.
        os.close(self.saved_stdout_fd)
        os.close(self.saved_stderr_fd)

        # Close the log file.
        if self.logfile:
            self.logfile.close()



def isThisEngaging():
    try:
        hostname = os.environ["SLURM_SUBMIT_HOST"][:6]
    except:
        try:
            hostname = os.environ["HOSTNAME"][:6]
        except:
            return False

    bo = hostname in ["eofe7.", "eofe8.", "eofe10"]

    print(f"\t- Is this engaging? {hostname}: {bo}")

    return bo


def machineSettings(
    code="tgyro",
    nameScratch="mitim_tmp/",
    forceUsername=None,
):
    """
    This script uses the config json file and completes the information required to run each code

    forceUsername is used to override the json file (for TRANSP PRF), adding also an identity and scratch
    """

    # Determine where to run this code, depending on config file
    s = load_settings()
    machine = s["preferences"][code]

    """
    Set-up per code and machine
    -------------------------------------------------
    """

    if forceUsername is not None:
        username = forceUsername
        scratch = f"/home/{username}/scratch/{nameScratch}"
    else:
        username = s[machine]["username"] if ("username" in s[machine]) else "dummy"
        scratch = f"{s[machine]['scratch']}/{nameScratch}"

    machineSettings = {
        "machine": s[machine]["machine"],
        "user": username,
        "tunnel": None,
        "port": None,
        "identity": None,
        "modules": "source $MITIM_PATH/config/mitim.bashrc",
        "folderWork": scratch,
        "slurm": {},
        "isTunnelSameMachine": (
            bool(s[machine]["isTunnelSameMachine"])
            if "isTunnelSameMachine" in s[machine]
            else False
        ),
    }

    # I can give extra things to load in the config file
    if (
        "modules" in s[machine]
        and s[machine]["modules"] is not None
        and s[machine]["modules"] != ""
    ):
        machineSettings["modules"] = (
            f'{machineSettings["modules"]}\n{s[machine]["modules"]}'
        )

    checkers = ["slurm", "identity", "tunnel", "port"]
    for i in checkers:
        if i in s[machine]:
            machineSettings[i] = s[machine][i]

    if "scratch_tunnel" in s[machine]:
        machineSettings["folderWorkTunnel"] = (
            f"{s[machine]['scratch_tunnel']}/{nameScratch}"
        )

    # ************************************************************************************************************************
    # Specific case of being already in the machine where I need to run
    # ************************************************************************************************************************

    # Am I already in this machine?
    if machine in socket.gethostname():
        # Avoid tunneling and porting if I'm already there
        machineSettings["tunnel"] = machineSettings["port"] = None

        # Avoid sshing if I'm already there except if I'm running with another specific user
        if (forceUsername is None) or (forceUsername == getpass.getuser()):
            machineSettings["machine"] = "local"

    # ************************************************************************************************************************

    if machineSettings["machine"] == "local":
        machineSettings["folderWork"] = IOtools.expandPath(
            machineSettings["folderWork"]
        )

    if forceUsername is not None:
        machineSettings["identity"] = f"~/.ssh/id_rsa_{forceUsername}"

    return machineSettings
