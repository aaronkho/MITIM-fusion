import sys
import numpy as np
from mitim_tools.misc_tools import IOtools
from IPython import embed

from mitim_tools.misc_tools.IOtools import printMsg as print

"""
This is used to commpare namelists values
e.g.
		compareNML.py namelist1TR.DAT namelist2TR.DAT =

"""


def compareNML(file1, file2, commentCommand="!", separator="=", precision_of=None):
    d1 = IOtools.generateMITIMNamelist(
        file1, commentCommand=commentCommand, separator=separator
    )
    d2 = IOtools.generateMITIMNamelist(
        file2, commentCommand=commentCommand, separator=separator
    )

    d1 = separateArrays(d1)
    d2 = separateArrays(d2)

    diff = compareDictionaries(d1, d2, precision_of = precision_of)

    diffo = cleanDifferences(diff)

    k = sorted([i for i in diffo.keys()])
    diff = IOtools.CaseInsensitiveDict()
    for i in k:
        diff[i] = diffo[i]

    return diff


def separateArrays(d):
    # Separate values in commas
    dnew = IOtools.CaseInsensitiveDict()
    for ikey in d:
        if isinstance(d[ikey], str) and "," in d[ikey]:
            arr = d[ikey].split(",")
            for cont, i in enumerate(arr):
                try:
                    conv = float(i)
                except:
                    conv = i
                dnew[ikey + f"({cont + 1})"] = conv
        else:
            dnew[ikey] = d[ikey]

    # Quotes
    for ikey in dnew:
        if isinstance(dnew[ikey], str) and "'" in dnew[ikey]:
            dnew[ikey] = dnew[ikey].replace("'", '"')

    return dnew


def cleanDifferences(d, tol_rel=1e-7):
    d_new = {}
    for key in d:
        if key not in ["inputdir"]:
            if (
                d[key][0] is None
                or d[key][1] is None
                or isinstance(d[key][0], str)
                or isinstance(d[key][1], str)
                or isinstance(d[key][0], bool)
                or isinstance(d[key][1], bool)
                or d[key][0] == 0
                or np.abs((d[key][0] - d[key][1]) / d[key][0]) > tol_rel
            ):
                d_new[key] = d[key]

    return d_new

def compare_number(a,b,precision_of=None):

    if precision_of is None:
        a_rounded = a
        b_rounded = b

    elif precision_of == 1:
        # Round to the same number of decimal places
        a_str = str(a)
        if '.' in a_str:
            decimal_places = len(a_str.split('.')[1])
        else:
            decimal_places = 0

        b_rounded = round(b, decimal_places)
        a_rounded = a

    elif precision_of == 2:

        # Round to the same number of significant figures
        b_str = str(b)
        if '.' in b_str:
            decimal_places = len(b_str.split('.')[1])
        else:
            decimal_places = 0

        b_rounded = b
        a_rounded = round(a, decimal_places)

    # Compare the two numbers
    are_equal = (a_rounded == b_rounded)

    return are_equal

def compareDictionaries(d1, d2, precision_of=None):
    different = {}

    for key in d1:
        # Exists in d1 but not in d2
        if key not in d2:
            different[key] = [d1[key], None]
        # Values are different
        else:
            if not compare_number(d1[key],d2[key],precision_of=precision_of):
                different[key] = [d1[key], d2[key]]

    for key in d2:
        # Exists in d2 but not in d1
        if key not in d1:
            different[key] = [None, d2[key]]

    return different


def printTable(diff, warning_percent=1e-1):
    try:
        print(f"{'':>15}{file1.split('/')[-1]:>25}{file2.split('/')[-1]:>25}")
    except:
        pass
    for key in diff:
        if diff[key][0] is not None:
            if diff[key][1] is not None:
                if diff[key][0] != 0.0:
                    try:
                        perc = 100 * np.abs(
                            (diff[key][0] - diff[key][1]) / diff[key][0]
                        )
                    except:
                        perc = np.nan
                else:
                    perc = np.nan
                print(
                    f"{key:>15}{str(diff[key][0]):>25}{str(diff[key][1]):>25}  (~{perc:.0e}%)",
                    typeMsg="w" if perc > warning_percent else "",
                )
            else:
                print(f"{key:>15}{str(diff[key][0]):>25}{'':>25}")
        else:
            print(f"{key:>15}{'':>25}{str(diff[key][1]):>25}")
        print(
            "--------------------------------------------------------------------------------"
        )


if __name__ == "__main__":
    file1 = sys.argv[1]
    file2 = sys.argv[2]

    try:
        separator = sys.argv[3]
    except:
        separator = "="

    diff = compareNML(file1, file2, separator=separator)

    printTable(diff)
    print(f"Differences: {len(diff)}")
