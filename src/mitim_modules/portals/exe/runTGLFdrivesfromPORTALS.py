import argparse
from IPython import embed
from mitim_modules.portals.aux import PORTALSanalysis

"""

This script is useful to understand why MITIM may fail at reproducing TGLF fluxes. You can select the iteration
to use as base case to see how TGLF behaves (understand if it has discontinuities)
	e.g.
		runTGLFdrivesfrommitim.py --folder run11/ --ev -1 --pos 0 2 --var 0.05  --wf 0.2 1.0

Notes:
	- wf runs scan with waveform too (slightly more expensive, as it will require 1 extra sim per run, but cheaper)
"""

# --- Inputs

parser = argparse.ArgumentParser()
parser.add_argument("--folder", required=True, type=str)
parser.add_argument("--ev", type=int, required=False, default=-1)
parser.add_argument("--pos", type=int, required=False, default=[0.5], nargs="*")
parser.add_argument("--wf", type=float, required=False, default=None, nargs="*")
parser.add_argument(
    "--var", type=float, required=False, default=0.01
)  # Variation in inputs (1% default)

args = parser.parse_args()
folder = args.folder
ev = args.ev
pos = args.pos
wf = args.wf
var = args.var

# --- Workflow

portals = PORTALSanalysis.PORTALSanalyzer(folder)
tglf, TGLFsettings, extraOptions = portals.extractTGLF(folder=f"{folder}/turb_drives/",positions=pos,step=ev)

tglf.runScanTurbulenceDrives(
    subFolderTGLF="turb",
    resolutionPoints=5,
    variation=var,
    variablesDrives=["RLTS_1", "RLTS_2", "RLNS_1", "XNUE", "TAUS_2", "BETAE"],
    TGLFsettings=TGLFsettings,
    extraOptions=extraOptions,
    restart=False,
    runWaveForms=wf,
)

tglf.plotScanTurbulenceDrives(label="turb")
