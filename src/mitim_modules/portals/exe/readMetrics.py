import argparse
import matplotlib.pyplot as plt
from mitim_tools.misc_tools import IOtools
from mitim_modules.portals.aux import PORTALSanalysis

"""
This script is to plot only the convergence figure, not the rest of surrogates that takes long.
It also does it on a separate figure, so easy to manage (e.g. for saving as .eps)
"""

parser = argparse.ArgumentParser()
parser.add_argument("folders", type=str, nargs="*")
parser.add_argument("--remote","-r", type=str, required=False, default=None)

parser.add_argument(
    "--max", type=int, required=False, default=None
)  # Define max bounds of fluxes based on this one, like 0, -1 or None(best)
parser.add_argument("--index_extra", type=int, required=False, default=None)
parser.add_argument(
    "--all", required=False, default=False, action='store_true'
)  # Plot all fluxes?
parser.add_argument(
    "--file", type=str, required=False, default=None
)  # File to save .eps
parser.add_argument(
    "--complete", "-c", required=False, default=False, action='store_true'
)


args = parser.parse_args()


folders = args.folders

portals_total = []
for folderWork in folders:
    folderRemote_reduced = args.remote
    file = args.file
    indexToMaximize = args.max
    index_extra = args.index_extra
    plotAllFluxes = args.all
    complete = args.complete

    folderRemote = (
        f"{folderRemote_reduced}/{IOtools.reducePathLevel(folderWork)[-1]}/"
        if folderRemote_reduced is not None
        else None
    )

    # Read PORTALS
    portals = PORTALSanalysis.PORTALSanalyzer.from_folder(
        folderWork, folderRemote=folderRemote
    )

    portals_total.append(portals)
    
# PLOTTING

if not complete:
    size = 8
    plt.rc("font", family="serif", serif="Times", size=size)
    plt.rc("xtick.minor", size=size)
plt.close("all")

if (len(folders) == 1) and (not complete):
    plt.ion()
    fig = plt.figure(figsize=(15, 8))
    fn = None
else:
    from mitim_tools.misc_tools.GUItools import FigureNotebook
    plt.ioff()
    fn = FigureNotebook(0, "PORTALS", geometry="1600x1000")



for i in range(len(folders)):

    if (not complete) or isinstance(portals_total[i],PORTALSanalysis.PORTALSinitializer):
        if len(folders) > 1:
            fig = fn.add_figure(label=f"{IOtools.reducePathLevel(folders[i])[-1]}")

        portals_total[i].plotMetrics(
            fig = fig,
            fn = fn,
            indexToMaximize=indexToMaximize,
            plotAllFluxes=plotAllFluxes,
            index_extra=index_extra,
            file_save=file if len(folders) == 1 else None,
        )
    else:
        portals_total[i].plotPORTALS(fn=fn)

if (len(folders) > 1) or complete:    
    fn.show()
