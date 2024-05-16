import copy
import os
import torch
import numpy as np
from mitim_tools.misc_tools import PLASMAtools, IOtools
from mitim_tools.gacode_tools import TGYROtools, TGLFtools
from mitim_modules.portals.aux import PORTALScgyro
from mitim_tools.misc_tools.IOtools import printMsg as print
from IPython import embed


class power_transport:
    '''
    Default class for power transport models, change "evaluate" method to implement a new model
    '''
    def __init__(self, powerstate, name = "test", folder = "~/scratch/", extra_params = {}):

        self.name = name
        self.folder = folder
        self.extra_params = extra_params
        self.powerstate = powerstate

        # Allowed fluxes in powerstate so far
        self.quantities = ['Pe', 'Pi', 'Ce', 'CZ', 'Mt']

        self.variables = [f'{i}_tr' for i in self.quantities] + [f'{i}_tr_turb' for i in self.quantities] + [f'{i}_tr_neo' for i in self.quantities]

    def produce_profiles(self):

        if 'MODELparameters' in self.powerstate.TransportOptions["ModelOptions"] and 'applyCorrections' in self.powerstate.TransportOptions["ModelOptions"]["MODELparameters"]:
            applyCorrections = self.powerstate.TransportOptions["ModelOptions"]["MODELparameters"]["applyCorrections"]
        else:
            applyCorrections = {}

        # Write this updated profiles class (with parameterized profiles)
        self.file_profs = f"{IOtools.expandPath(self.folder)}/input.gacode"
        self.profiles = self.powerstate.insertProfiles(
            self.powerstate.profiles,
            writeFile=self.file_profs,
            applyCorrections=applyCorrections,
        )

        # copy for future modifications
        self.file_profs_mod = f"{self.file_profs}_modified"
        os.system(f"cp {self.file_profs} {self.file_profs_mod}")

    def evaluate(self):
        print("Nothing to evaluate", typeMsg="w")

        for i in self.variables:
            self.powerstate.plasma[i] = self.powerstate.plasma["te"][:, 1:] * 0.0

        for i in self.quantities:
            self.powerstate.plasma[i] = self.powerstate.plasma[i][:, 1:]

        self.results, self.model_results = None, None

    def clean(self):

         # Make sure that the variables are on-repeat
        for i in self.variables:
            self.powerstate.keys1D_derived[i] = 1

# ----------------------------------------------------------------------------------------------------
# FULL TGYRO
# ----------------------------------------------------------------------------------------------------

class tgyro_model(power_transport):
    def __init__(self, powerstate, name="test", folder="~/scratch/", extra_params={}):
        super().__init__(powerstate, name, folder, extra_params)

    def evaluate(self):

        FolderEvaluation_TGYRO  = IOtools.expandPath(self.folder)
        TransportOptions        = self.powerstate.TransportOptions
        provideTargets          = self.powerstate.TargetCalc == "tgyro"
        ProfilesPredicted       = self.powerstate.ProfilesPredicted
        dfT                     = self.powerstate.dfT
    
        # ------------------------------------------------------------------------------------------------------------------------
        # Model Options
        # ------------------------------------------------------------------------------------------------------------------------

        MODELparameters = TransportOptions["ModelOptions"]["MODELparameters"]
        
        includeFast = TransportOptions["ModelOptions"].get("includeFastInQi",False)
        impurityPosition = TransportOptions["ModelOptions"].get("impurityPosition", 1)
        useConvectiveFluxes = TransportOptions["ModelOptions"].get("useConvectiveFluxes", True)
        UseFineGridTargets = TransportOptions["ModelOptions"].get("UseFineGridTargets", False)
        launchMODELviaSlurm = TransportOptions["ModelOptions"].get("launchMODELviaSlurm", False)
        restart = TransportOptions["ModelOptions"].get("restart", False)
        provideTurbulentExchange = TransportOptions["ModelOptions"].get("TurbulentExchange", False)
        profiles_postprocessing_fun = TransportOptions["ModelOptions"].get("profiles_postprocessing_fun", None)
        OriginalFimp = TransportOptions["ModelOptions"].get("OriginalFimp", 1.0)
        forceZeroParticleFlux = TransportOptions["ModelOptions"].get("forceZeroParticleFlux", False)
        percentError = TransportOptions["ModelOptions"].get("percentError", [5, 1, 0.5])
        
        labels_results = []

        # ------------------------------------------------------------------------------------------------------------------------
        # 1. tglf_neo_original: Run TGYRO workflow - TGLF + NEO in subfolder tglf_neo_original (original as in... without stds or merging)
        # ------------------------------------------------------------------------------------------------------------------------

        RadiisToRun = [
            self.powerstate.plasma["rho"][0, 1:][i].item()
            for i in range(len(self.powerstate.plasma["rho"][0, 1:]))
        ]

        tgyro = TGYROtools.TGYRO(cdf=dummyCDF(self.folder, FolderEvaluation_TGYRO))
        tgyro.prep(FolderEvaluation_TGYRO, profilesclass_custom=self.profiles)

        if launchMODELviaSlurm:
            print("\t- Launching TGYRO evaluation as a batch job")
        else:
            print("\t- Launching TGYRO evaluation as a terminal job")

        tgyro.run(
            subFolderTGYRO="tglf_neo_original/",
            restart=restart,
            forceIfRestart=True,
            special_radii=RadiisToRun,
            iterations=0,
            PredictionSet=[
                int("te" in ProfilesPredicted),
                int("ti" in ProfilesPredicted),
                int("ne" in ProfilesPredicted),
            ],
            TGLFsettings=MODELparameters["transport_model"]["TGLFsettings"],
            extraOptionsTGLF=MODELparameters["transport_model"]["extraOptionsTGLF"],
            TGYRO_physics_options=MODELparameters["Physics_options"],
            launchSlurm=launchMODELviaSlurm,
            minutesJob=5,
            forcedName=self.name,
        )

        tgyro.read(label="tglf_neo_original")

        # Copy one with evaluated targets
        self.file_profs_targets = f"{tgyro.FolderTGYRO}/input.gacode.new"

        # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
        # Run TGLF standalone --> In preparation for the transition
        # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$

        # tglf = TGLFtools.TGLF(rhos=RadiisToRun)
        # _ = tglf.prep(self.folder+'/stds/', inputgacode=self.file_profs, restart=restart)

        # tglf.run(
        #     subFolderTGLF="tglf_neo_original/",
        #     TGLFsettings=MODELparameters["transport_model"]["TGLFsettings"],
        #     restart=restart,
        #     forceIfRestart=True,
        #     extraOptions=MODELparameters["transport_model"]["extraOptionsTGLF"],
        #     launchSlurm=launchMODELviaSlurm,
        #     slurm_setup={"cores": 4, "minutes": 1},
        # )

        # tglf.read(label="tglf_neo_original")

        # results = tglf.tgyroing(label="tglf_neo_original")

        # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
        # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$

        # ------------------------------------------------------------------------------------------------------------------------
        # 2. tglf_neo: Write TGLF, NEO and TARGET errors in tgyro files as well
        # ------------------------------------------------------------------------------------------------------------------------

        # Copy original TGYRO folder
        if os.path.exists(f"{FolderEvaluation_TGYRO}/tglf_neo/"):
            os.system(f"{FolderEvaluation_TGYRO}/tglf_neo/")
        os.system(
            f"cp -r {FolderEvaluation_TGYRO}/tglf_neo_original {FolderEvaluation_TGYRO}/tglf_neo"
        )

        # Add errors and merge fluxes as we would do if this was a CGYRO run
        curateTGYROfiles(
            tgyro.results["tglf_neo_original"],
            f"{FolderEvaluation_TGYRO}/tglf_neo/",
            percentError,
            impurityPosition=impurityPosition,
            includeFast=includeFast,
        )

        # Read again to capture errors
        tgyro.read(
            label="tglf_neo", folder=f"{FolderEvaluation_TGYRO}/tglf_neo/"
        )
        labels_results.append("tglf_neo")

        # Produce right quantities

        TGYROresults = tgyro.results["tglf_neo"]

        portals_variables = TGYROresults.TGYROmodeledVariables(
            useConvectiveFluxes=useConvectiveFluxes,
            includeFast=includeFast,
            impurityPosition=impurityPosition,
            UseFineGridTargets=UseFineGridTargets,
            OriginalFimp=OriginalFimp,
            forceZeroParticleFlux=forceZeroParticleFlux,
            dfT=dfT,
        )

        # ------------------------------------------------------------------------------------------------------------------------
        # 3. cgyro_neo: Trick to fake a tgyro output to reflect CGYRO
        # ------------------------------------------------------------------------------------------------------------------------

        if TransportOptions == "cgyro_neo-tgyro":
            portals_variables_orig = copy.deepcopy(portals_variables)

            print(
                "\t- Checking whether cgyro_neo folder exists and it was written correctly via cgyro_trick..."
            )

            correctly_run = os.path.exists(f"{FolderEvaluation_TGYRO}/cgyro_neo")
            if correctly_run:
                print("\t\t- Folder exists, but was cgyro_trick run?")
                with open(f"{FolderEvaluation_TGYRO}/cgyro_neo/mitim_flag", "r") as f:
                    correctly_run = bool(float(f.readline()))

            if correctly_run:
                print("\t\t\t* Yes, it was", typeMsg="w")
            else:
                print("\t\t\t* No, it was not, repating process", typeMsg="i")

                # Copy tglf_neo results
                os.system(
                    f"cp -r {FolderEvaluation_TGYRO}/tglf_neo {FolderEvaluation_TGYRO}/cgyro_neo"
                )

                # CGYRO writter
                cgyro_trick(
                    self.powerstate,
                    f"{FolderEvaluation_TGYRO}/cgyro_neo",
                    portals_variables=portals_variables,
                    profiles_postprocessing_fun=profiles_postprocessing_fun,
                    extra_params=self.extra_params,
                    name=self.name,
                )

            # Read TGYRO files and construct portals variables

            tgyro.read(
                label="cgyro_neo", folder=f"{FolderEvaluation_TGYRO}/cgyro_neo"
            )  # Re-read TGYRO to store
            TGYROresults = tgyro.results["cgyro_neo"]
            labels_results.append("cgyro_neo")

            portals_variables = TGYROresults.TGYROmodeledVariables(
                useConvectiveFluxes=useConvectiveFluxes,
                includeFast=includeFast,
                impurityPosition=impurityPosition,
                UseFineGridTargets=UseFineGridTargets,
                OriginalFimp=OriginalFimp,
                forceZeroParticleFlux=forceZeroParticleFlux,
                dfT=dfT,
            )

            print("\t- Checking model modifications:")
            for r in ["Qe_turb", "Qi_turb", "Ge_turb", "GZ_turb", "Mt_turb", "PexchTurb"]:
                print(
                    f"\t\t{r}(tglf)  = {'  '.join([f'{k:.1e} (+-{ke:.1e})' for k,ke in zip(portals_variables_orig[r][0][1:],portals_variables_orig[r+'_stds'][0][1:]) ])}"
                )
                print(
                    f"\t\t{r}(cgyro) = {'  '.join([f'{k:.1e} (+-{ke:.1e})' for k,ke in zip(portals_variables[r][0][1:],portals_variables[r+'_stds'][0][1:]) ])}"
                )

            # **
            tgyro.results["use"] = tgyro.results["cgyro_neo"]

        else:
            # copy profiles too!
            profilesToShare(self)

            # **
            tgyro.results["use"] = tgyro.results["tglf_neo"]

        labels_results.append("use")

        # --------------------------------------------------------------------------------------------------------------------------------
        # TURBULENCE and NEOCLASSICAL
        # --------------------------------------------------------------------------------------------------------------------------------

        iteration = 0
        tuple_rho_indeces = ()
        for rho in tgyro.rhosToSimulate:
            tuple_rho_indeces += (np.argmin(np.abs(rho - TGYROresults.rho)),)

        mapper = {
            "Pe_tr_turb": "Qe_turb",
            "Pi_tr_turb": "Qi_turb",
            "Ce_tr_turb": "Ge_turb",
            "CZ_tr_turb": "GZ_turb",
            "Mt_tr_turb": "Mt_turb",
            "Pe_tr_neo": "Qe_neo",
            "Pi_tr_neo": "Qi_neo",
            "Ce_tr_neo": "Ge_neo",
            "CZ_tr_neo": "GZ_neo",
            "Mt_tr_neo": "Mt_neo",
        }

        if provideTurbulentExchange:
            mapper.update(
                {"PexchTurb": "PexchTurb"}
            )  # I need to do this outside of provideTargets because powerstate cannot compute this

        if provideTargets:
            mapper.update(
                {
                    "Pe": "Qe",
                    "Pi": "Qi",
                    "Ce": "Ge",
                    "CZ": "GZ",
                    "Mt": "Mt",
                }
            )
        else:
            self.powerstate.plasma["Pe"] = self.powerstate.plasma["Pe"][:, 1:]
            self.powerstate.plasma["Pi"] = self.powerstate.plasma["Pi"][:, 1:]
            self.powerstate.plasma["Ce"] = self.powerstate.plasma["Ce"][:, 1:]
            self.powerstate.plasma["CZ"] = self.powerstate.plasma["CZ"][:, 1:]
            self.powerstate.plasma["Mt"] = self.powerstate.plasma["Mt"][:, 1:]

            percentErrorTarget = percentError[2] / 100.0

            self.powerstate.plasma["Pe_stds"] = abs(self.powerstate.plasma["Pe"]) * percentErrorTarget
            self.powerstate.plasma["Pi_stds"] = abs(self.powerstate.plasma["Pi"]) * percentErrorTarget
            self.powerstate.plasma["Ce_stds"] = abs(self.powerstate.plasma["Ce"]) * percentErrorTarget
            self.powerstate.plasma["CZ_stds"] = abs(self.powerstate.plasma["CZ"]) * percentErrorTarget
            self.powerstate.plasma["Mt_stds"] = abs(self.powerstate.plasma["Mt"]) * percentErrorTarget

        for ikey in mapper:
            self.powerstate.plasma[ikey] = (
                torch.from_numpy(
                    portals_variables[mapper[ikey]][iteration, tuple_rho_indeces]
                )
                .to(dfT)
                .unsqueeze(0)
            )
            self.powerstate.plasma[ikey + "_stds"] = (
                torch.from_numpy(
                    portals_variables[mapper[ikey] + "_stds"][iteration, tuple_rho_indeces]
                )
                .to(dfT)
                .unsqueeze(0)
            )

        # ------------------------------------------------------------------------------------------------------------------------
        # Sum here, after modifications
        # ------------------------------------------------------------------------------------------------------------------------

        self.powerstate.plasma["Pe_tr"] = self.powerstate.plasma["Pe_tr_turb"] + self.powerstate.plasma["Pe_tr_neo"]
        self.powerstate.plasma["Pi_tr"] = self.powerstate.plasma["Pi_tr_turb"] + self.powerstate.plasma["Pi_tr_neo"]
        self.powerstate.plasma["Ce_tr"] = self.powerstate.plasma["Ce_tr_turb"] + self.powerstate.plasma["Ce_tr_neo"]
        self.powerstate.plasma["CZ_tr"] = self.powerstate.plasma["CZ_tr_turb"] + self.powerstate.plasma["CZ_tr_neo"]
        self.powerstate.plasma["Mt_tr"] = self.powerstate.plasma["Mt_tr_turb"] + self.powerstate.plasma["Mt_tr_neo"]

        # ------------------------------------------------------------------------------------------------------------------------
        # Results
        # ------------------------------------------------------------------------------------------------------------------------

        self.model_results = tgyro.results # Pass the TGYRO results class 

# ------------------------------------------------------------------
# SIMPLE Diffusion
# ------------------------------------------------------------------

class diffusion_model(power_transport):
    def __init__(self, powerstate, name="test", folder="~/scratch/", extra_params={}):
        super().__init__(powerstate, name, folder, extra_params)

    def evaluate(self):

        Pe_tr = PLASMAtools.conduction(
            self.powerstate.plasma["ne"],
            self.powerstate.plasma["te"],
            self.powerstate.TransportOptions["ModelOptions"]["chi_e"],
            self.plasma["aLte"],
            self.plasma["a"],
        )
        Pi_tr = PLASMAtools.conduction(
            self.powerstate.plasma["ni"].sum(axis=-1),
            self.powerstate.plasma["ti"],
            self.powerstate.TransportOptions["ModelOptions"]["chi_i"],
            self.powerstate.plasma["aLti"],
            self.powerstate.plasma["a"],
        )

        self.powerstate.plasma["Pe_tr_turb"] = Pe_tr[:, 1:] * 2 / 3
        self.powerstate.plasma["Pi_tr_turb"] = Pi_tr[:, 1:] * 2 / 3

        self.powerstate.plasma["Pe_tr_neo"] = Pe_tr[:, 1:] * 1 / 3
        self.powerstate.plasma["Pi_tr_neo"] = Pi_tr[:, 1:] * 1 / 3

        self.powerstate.plasma["Pe_tr"] = self.powerstate.plasma["Pe_tr_turb"] + self.powerstate.plasma["Pe_tr_neo"]
        self.powerstate.plasma["Pi_tr"] = self.powerstate.plasma["Pi_tr_turb"] + self.powerstate.plasma["Pi_tr_neo"]

        self.powerstate.plasma["Pe"] = self.powerstate.plasma["Pe"][:, 1:]  # This should be fixed later
        self.powerstate.plasma["Pi"] = self.powerstate.plasma["Pi"][:, 1:]  # This should be fixed later

        self.powerstate.plasma["Ce_tr_turb"] = self.powerstate.plasma["Pe_tr"] * 0.0
        self.powerstate.plasma["Ce_tr_neo"] = self.powerstate.plasma["Pe_tr"] * 0.0
        self.powerstate.plasma["Ce_tr"] = self.powerstate.plasma["Pe_tr"] * 0.0
        self.powerstate.plasma["Ce"] = self.powerstate.plasma["Pe"] * 0.0

        # ------------------------------------------------------------------------------------------------------------------------
        self.results = None


# ------------------------------------------------------------------
# SURROGATE
# ------------------------------------------------------------------

class surrogate_model(power_transport):
    def __init__(self, powerstate, name="test", folder="~/scratch/", extra_params={}):
        super().__init__(powerstate, name, folder, extra_params)

    def evaluate(self):

        """
        flux_fun as given in ModelOptions must produce Q and Qtargets in order of te,ti,ne
        """

        Q, QT = self.powerstate.TransportOptions["ModelOptions"]["flux_fun"](self.Xcurrent[0])

        numeach = self.powerstate.plasma["rho"].shape[1] - 1

        for c, i in enumerate(self.powerstate.ProfilesPredicted):
            if i == "te":
                self.powerstate.plasma["Pe_tr"] = Q[:, numeach * c : numeach * (c + 1)]
            if i == "ti":
                self.powerstate.plasma["Pi_tr"] = Q[:, numeach * c : numeach * (c + 1)]
            if i == "ne":
                self.powerstate.plasma["Ce_tr"] = Q[:, numeach * c : numeach * (c + 1)]
            if i == "nZ":
                self.powerstate.plasma["CZ_tr"] = Q[:, numeach * c : numeach * (c + 1)]

        for c2, i in enumerate(self.powerstate.ProfilesPredicted):
            if i == "te":
                self.powerstate.plasma["Pe"] = QT[:, numeach * c2 : numeach * (c2 + 1)]
            if i == "ti":
                self.powerstate.plasma["Pi"] = QT[:, numeach * c2 : numeach * (c2 + 1)]
            if i == "ne":
                self.powerstate.plasma["Ce"] = QT[:, numeach * c2 : numeach * (c2 + 1)]
            if i == "nZ":
                self.powerstate.plasma["CZ"] = QT[:, numeach * c2 : numeach * (c2 + 1)]


def curateTGYROfiles(
    tgyro, folder, percentError, impurityPosition=1, includeFast=False
):
    # TGLF ---------------------------------------------------------------------------------------------------------

    Qe = tgyro.Qe_sim_turb[0, 1:]
    if includeFast:
        Qi = tgyro.QiIons_sim_turb[0, 1:]
    else:
        Qi = tgyro.QiIons_sim_turb_thr[0, 1:]
    Ge = tgyro.Ge_sim_turb[0, 1:]
    GZ = tgyro.Gi_sim_turb[impurityPosition - 1, 0, 1:]
    Mt = tgyro.Mt_sim_turb[0, 1:]
    Pexch = tgyro.EXe_sim_turb[0, 1:]

    percentErrorTGLF = percentError[0] / 100.0

    QeE = abs(tgyro.Qe_sim_turb[0, 1:]) * percentErrorTGLF
    if includeFast:
        QiE = abs(tgyro.QiIons_sim_turb[0, 1:]) * percentErrorTGLF
    else:
        QiE = abs(tgyro.QiIons_sim_turb_thr[0, 1:]) * percentErrorTGLF
    GeE = abs(tgyro.Ge_sim_turb[0, 1:]) * percentErrorTGLF
    GZE = abs(tgyro.Gi_sim_turb[impurityPosition - 1, 0, 1:]) * percentErrorTGLF
    MtE = abs(tgyro.Mt_sim_turb[0, 1:]) * percentErrorTGLF
    PexchE = abs(tgyro.EXe_sim_turb[0, 1:]) * percentErrorTGLF

    # Neo ----------------------------------------------------------------------------------------------------------

    QeNeo = tgyro.Qe_sim_neo[0, 1:]
    if includeFast:
        QiNeo = tgyro.QiIons_sim_neo[0, 1:]
    else:
        QiNeo = tgyro.QiIons_sim_neo_thr[0, 1:]
    GeNeo = tgyro.Ge_sim_neo[0, 1:]
    GZNeo = tgyro.Gi_sim_neo[impurityPosition - 1, 0, 1:]
    MtNeo = tgyro.Mt_sim_neo[0, 1:]

    percentErrorNeo = percentError[1] / 100.0

    QeNeoE = abs(tgyro.Qe_sim_neo[0, 1:]) * percentErrorNeo
    if includeFast:
        QiNeoE = abs(tgyro.QiIons_sim_neo[0, 1:]) * percentErrorNeo
    else:
        QiNeoE = abs(tgyro.QiIons_sim_neo_thr[0, 1:]) * percentErrorNeo
    GeNeoE = abs(tgyro.Ge_sim_neo[0, 1:]) * percentErrorNeo
    GZNeoE = abs(tgyro.Gi_sim_neo[impurityPosition - 1, 0, 1:]) * percentErrorNeo
    MtNeoE = abs(tgyro.Mt_sim_neo[0, 1:]) * percentErrorNeo

    # Merge

    PORTALScgyro.modifyFLUX(
        tgyro,
        folder,
        Qe,
        Qi,
        Ge,
        GZ,
        Mt,
        Pexch,
        QeNeo=QeNeo,
        QiNeo=QiNeo,
        GeNeo=GeNeo,
        GZNeo=GZNeo,
        MtNeo=MtNeo,
        impurityPosition=impurityPosition,
    )

    PORTALScgyro.modifyFLUX(
        tgyro,
        folder,
        QeE,
        QiE,
        GeE,
        GZE,
        MtE,
        PexchE,
        QeNeo=QeNeoE,
        QiNeo=QiNeoE,
        GeNeo=GeNeoE,
        GZNeo=GZNeoE,
        MtNeo=MtNeoE,
        impurityPosition=impurityPosition,
        special_label="_stds",
    )

    # Targets -------------------------------------------------------------------------------------------------------

    percentErrorTarget = percentError[2] / 100.0

    QeTargetE = abs(tgyro.Qe_tar[0, 1:]) * percentErrorTarget
    QiTargetE = abs(tgyro.Qi_tar[0, 1:]) * percentErrorTarget
    GeTargetE = abs(tgyro.Ge_tar[0, 1:]) * percentErrorTarget
    GZTargetE = GeTargetE * 0.0
    MtTargetE = abs(tgyro.Mt_tar[0, 1:]) * percentErrorTarget

    PORTALScgyro.modifyEVO(
        tgyro,
        folder,
        QeTargetE * 0.0,
        QiTargetE * 0.0,
        GeTargetE * 0.0,
        GZTargetE * 0.0,
        MtTargetE * 0.0,
        impurityPosition=impurityPosition,
        positionMod=1,
        special_label="_stds",
    )
    PORTALScgyro.modifyEVO(
        tgyro,
        folder,
        QeTargetE,
        QiTargetE,
        GeTargetE,
        GZTargetE,
        MtTargetE,
        impurityPosition=impurityPosition,
        positionMod=2,
        special_label="_stds",
    )


def profilesToShare(self):
    if "folder" in self.extra_params:
        whereFolder = IOtools.expandPath(
            self.extra_params["folder"] + "/Outputs/ProfilesEvaluated/"
        )
        if not os.path.exists(whereFolder):
            IOtools.askNewFolder(whereFolder)

        fil = f"{whereFolder}/input.gacode.{self.extra_params['numPORTALS']}"
        os.system(f"cp {self.file_profs_mod} {fil}")
        os.system(f"cp {self.file_profs} {fil}_unmodified")
        os.system(f"cp {self.file_profs_targets} {fil}_unmodified.new")
        print(f"\t- Copied profiles to {IOtools.clipstr(fil)}")
    else:
        print("\t- Could not move files", typeMsg="w")


def cgyro_trick(
    self,
    FolderEvaluation_TGYRO,
    portals_variables=None,
    profiles_postprocessing_fun=None,
    extra_params={},
    name="",
):
    with open(f"{FolderEvaluation_TGYRO}/mitim_flag", "w") as f:
        f.write("0")

    # **************************************************************************************************************************
    # Print Information
    # **************************************************************************************************************************

    if portals_variables is not None:
        txt = "\nFluxes to be matched by CGYRO ( TARGETS - NEO ):"

        for var, varn in zip(
            ["r/a  ", "rho  ", "a/LTe", "a/LTi", "a/Lne", "a/LnZ", "a/Lw0"],
            ["roa", "rho", "aLte", "aLti", "aLne", "aLnZ", "aLw0"],
        ):
            txt += f"\n{var}        = "
            for j in range(self.plasma["rho"].shape[1] - 1):
                txt += f"{self.plasma[varn][0,j+1]:.6f}   "

        for var, varn in zip(
            ["Qe (MW/m^2)", "Qi (MW/m^2)", "Ce (MW/m^2)", "CZ (MW/m^2)", "Mt (J/m^2) "],
            ["Qe", "Qi", "Ge", "GZ", "Mt"],
        ):
            txt += f"\n{var}  = "
            for j in range(self.plasma["rho"].shape[1] - 1):
                txt += f"{portals_variables[varn][0,j+1]-portals_variables[f'{varn}_neo'][0,j+1]:.4e}   "

        print(txt)

    # **************************************************************************************************************************
    # Modification to input.gacode (e.g. lump impurities)
    # **************************************************************************************************************************

    if profiles_postprocessing_fun is not None:
        print(
            f"\t- Modifying input.gacode.modified to run transport calculations based on {profiles_postprocessing_fun}",
            typeMsg="i",
        )
        profiles = profiles_postprocessing_fun(self.file_profs_mod)

    # Copy profiles so that later it is easy to grab all the input.gacodes that were evaluated
    profilesToShare(self)

    # **************************************************************************************************************************
    # Evaluate CGYRO
    # **************************************************************************************************************************

    PORTALScgyro.evaluateCGYRO(
        extra_params["PORTALSparameters"],
        extra_params["folder"],
        extra_params["numPORTALS"],
        FolderEvaluation_TGYRO,
        self.file_profs,
        rad=self.plasma["rho"].shape[1] - 1,
    )

    # **************************************************************************************************************************
    # EXTRA
    # **************************************************************************************************************************

    # Make tensors
    for i in ["Pe_tr_turb", "Pi_tr_turb", "Ce_tr_turb", "CZ_tr_turb", "Mt_tr_turb"]:
        try:
            self.plasma[i] = torch.from_numpy(self.plasma[i]).to(self.dfT).unsqueeze(0)
        except:
            pass

    # Write a flag indicating this was performed, to avoid an issue that... the script crashes when it has copied tglf_neo, without cgyro_trick modification
    with open(f"{FolderEvaluation_TGYRO}/mitim_flag", "w") as f:
        f.write("1")

def dummyCDF(GeneralFolder, FolderEvaluation):
    """
    This routine creates path to a dummy CDF file in FolderEvaluation, with the name "simulation_evaluation.CDF"

    GeneralFolder, e.g.    ~/runs_portals/run10/
    FolderEvaluation, e.g. ~/runs_portals/run10000/Execution/Evaluation.0//model_complete/
    """

    # ------- Name construction for scratch folders in parallel ----------------

    GeneralFolder = IOtools.expandPath(GeneralFolder, ensurePathValid=True)

    subname = GeneralFolder.split("/")[-1]  # run10 (simulation)
    if len(subname) == 0:
        subname = GeneralFolder.split("/")[-2]

    name = FolderEvaluation.split(".")[-1].split("/")[0]  # 0 	(evaluation #)

    cdf = f"{FolderEvaluation}/{subname}_ev{name}.CDF"

    return cdf
