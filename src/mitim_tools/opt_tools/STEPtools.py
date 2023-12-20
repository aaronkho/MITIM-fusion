import os, copy, datetime, torch, botorch
from IPython import embed
import dill as pickle_dill
import numpy as np
import matplotlib.pyplot as plt
from collections import OrderedDict
from mitim_tools.misc_tools import IOtools, MATHtools
from mitim_tools.opt_tools import SURROGATEtools, OPTtools, BOTORCHtools
from mitim_tools.opt_tools.aux import TESTtools
from mitim_tools.opt_tools.aux import BOgraphics
from mitim_tools.misc_tools.IOtools import printMsg as print


def identity(X, *args):
    return X, {}


def identityOutputs(X, *args):
    return torch.ones(X.shape[:-1]).unsqueeze(-1)


class OPTstep:
    def __init__(
        self,
        train_X,
        train_Y,
        train_Ystd,
        bounds,
        stepSettings={},
        surrogate_parameters={},
        StrategyOptions={},
        BOmetrics=None,
        currentIteration=1,
    ):
        """
        train_Ystd is in standard deviations (square root of the variance), absolute magnitude
        Rule: X_Y are provided in absolute units. Normalization has to happen inside each surrogate_model,
                and de-normalized before giving results to the outside of the function
        """

        self.train_X, self.train_Y, self.train_Ystd = train_X, train_Y, train_Ystd

        """
		Check dimensions
			- train_X should be (num_train,dimX)
			- train_Y should be (num_train,dimY)
			- train_Ystd should be (num_train,dimY) or just one float representing all values
		"""

        if len(self.train_X.shape) < 2:
            print(
                "--> train x only had 1 dimension, assuming that it has only 1 dimension"
            )
            self.train_X = np.transpose(np.atleast_2d(self.train_X))

        if len(self.train_Y.shape) < 2:
            print(
                "--> train y only had 1 dimension, assuming that it has only 1 dimension"
            )
            self.train_Y = np.transpose(np.atleast_2d(self.train_Y))

        if (
            isinstance(self.train_Ystd, float)
            or isinstance(self.train_Ystd, int)
            or len(self.train_Ystd.shape) < 2
        ):
            print(
                "--> train y noise only had 1 value only, assuming constant (std dev) for all samples in absolute terms"
            )
            if self.train_Ystd > 0:
                print(
                    "--> train y noise only had 1 value only, assuming constant (std dev) for all samples in absolute terms"
                )
                self.train_Ystd = self.train_Y * 0.0 + self.train_Ystd
            else:
                print(
                    "--> train y noise only had 1 value only, assuming constant (std dev) for all samples in relative terms"
                )
                self.train_Ystd = self.train_Y * np.abs(self.train_Ystd)

        if len(self.train_Ystd.shape) < 2:
            print(
                "--> train y noise only had 1 dimension, assuming that it has only 1 dimension"
            )
            self.train_Ystd = np.transpose(np.atleast_2d(self.train_Ystd))

        # **** Get argumnets into this class

        self.bounds = bounds
        self.stepSettings = stepSettings
        self.BOmetrics = BOmetrics
        self.currentIteration = currentIteration
        self.StrategyOptions = StrategyOptions

        # **** Step settings
        self.surrogateOptions = self.stepSettings["Optim"]["surrogateOptions"]
        self.acquisitionType = self.stepSettings["Optim"]["acquisitionType"]
        self.favorProximityType = self.stepSettings["Optim"]["favorProximityType"]
        self.optimizers = self.stepSettings["Optim"]["optimizers"]
        self.outputs = self.stepSettings["outputs"]
        self.dfT = self.stepSettings["dfT"]
        self.best_points_sequence = self.stepSettings["best_points_sequence"]
        self.fileOutputs = self.stepSettings["fileOutputs"]
        self.surrogate_parameters = surrogate_parameters

        # **** From standard deviation to variance
        self.train_Yvar = self.train_Ystd**2

    def fit_step(self, avoidPoints=[], fitWithTrainingDataIfContains=None):
        """
        Notes:
                - Note that fitWithTrainingDataIfContains = 'Tar' would only use the train_X,Y,Yvar tensors
                        to fit those surrogate variables that contain 'Tar' in their names. This is useful when in
                        mitim I want to simply use the training in a file and not directly from train_X,Y,Yvar for
                        the fluxes but I do want *new* target calculation
        """

        """
		*********************************************************************************************************************
			Preparing for fit
		*********************************************************************************************************************
		"""

        # Prepare case information. Copy because I'll be removing outliers
        self.x, self.y, self.yvar = (
            copy.deepcopy(self.train_X),
            copy.deepcopy(self.train_Y),
            copy.deepcopy(self.train_Yvar),
        )

        # Add outliers to avoid points (it cannot happen inside of SURROGATEtools or it will fail at combining)
        self.avoidPoints = copy.deepcopy(avoidPoints)
        self.curate_outliers()

        # Inform the surrogate physicsParams what iteration we are at by the number of points
        xTrain = self.x.shape[0] - len(self.avoidPoints)

        if self.surrogate_parameters["physicsInformedParams_dict"] is not None:
            self.surrogate_parameters[
                "physicsInformedParams"
            ] = self.surrogate_parameters["physicsInformedParams_dict"][
                list(self.surrogate_parameters["physicsInformedParams_dict"].keys())[
                    np.where(
                        xTrain
                        < np.array(
                            list(
                                self.surrogate_parameters[
                                    "physicsInformedParams_dict"
                                ].keys()
                            )
                        )
                    )[0][0]
                ]
            ]
        else:
            self.surrogate_parameters["physicsInformedParams"] = None

        if self.fileOutputs is not None:
            with open(self.fileOutputs, "a") as f:
                f.write("\n\n-----------------------------------------------------")
                f.write("\n * Fitting GP models to training data...")
        print(
            f"\n~~~~~~~ Performing fitting with {len(self.train_X)-len(self.avoidPoints)} training points ({len(self.avoidPoints)} avoided from {len(self.train_X)} total) ~~~~~~~~~~\n"
        )

        """
		*********************************************************************************************************************
			Prepare file with training data
		*********************************************************************************************************************
		"""

        fileTraining = f"{self.stepSettings['folderOutputs']}/DataTraining.pkl"
        data_dict = OrderedDict()
        for output in self.outputs:
            data_dict[output] = {
                "X": torch.tensor([]),
                "Y": torch.tensor([]),
                "Yvar": torch.tensor([]),
            }
        with open(fileTraining, "wb") as handle:
            pickle_dill.dump(data_dict, handle)

        """
		*********************************************************************************************************************
			Performing Fit
		*********************************************************************************************************************
		"""

        self.GP = {"individual_models": [None] * self.y.shape[-1]}

        print("--> Fitting multiple single-output models and creating composite model")
        time1 = datetime.datetime.now()

        for i in range(self.y.shape[-1]):
            outi = self.outputs[i] if (self.outputs is not None) else None

            # ----------------- specialTreatment is applied when I only want to use training data from a file, not from train_X
            specialTreatment = (
                (outi is not None)
                and (fitWithTrainingDataIfContains is not None)
                and (fitWithTrainingDataIfContains not in outi)
            )
            # -----------------------------------------------------------------------------------------------------------------------------------

            outi_transformed = (
                self.stepSettings["name_transformed_ofs"][i]
                if (self.stepSettings["name_transformed_ofs"] is not None)
                else outi
            )

            # ---------------------------------------------------------------------------------------------------
            # Define model-specific functions for this output
            # ---------------------------------------------------------------------------------------------------

            surrogateOptions = copy.deepcopy(self.surrogateOptions)

            # Then, depending on application (e.g. targets in mitim are fitted differently)
            if (
                "selectSurrogate" in surrogateOptions
                and surrogateOptions["selectSurrogate"] is not None
            ):
                surrogateOptions = surrogateOptions["selectSurrogate"](
                    outi, surrogateOptions
                )

            # ---------------------------------------------------------------------------------------------------
            # To avoid problems with fixed values (e.g. calibration terms that are fixed)
            # ---------------------------------------------------------------------------------------------------

            threshold_to_consider_fixed = 1e-6
            MaxRelativeDifference = np.abs(self.y.max() - self.y.min()) / np.abs(
                self.y.mean()
            )

            if (
                np.isnan(MaxRelativeDifference)
                or (
                    (self.y.shape[0] > 1)
                    and ((MaxRelativeDifference < threshold_to_consider_fixed).all())
                )
            ) and (not specialTreatment):
                print(
                    f"\t- Identified that outputs did not change, utilizing constant kernel for {outi}",
                    typeMsg="w",
                )
                FixedValue = True
                surrogateOptions["TypeMean"] = 0
                surrogateOptions["TypeKernel"] = 6  # Constant kernel

            else:
                FixedValue = False

            # ---------------------------------------------------------------------------------------------------
            # Fit individual output
            # ---------------------------------------------------------------------------------------------------

            # Data to train the surrogate
            x = self.x
            y = np.expand_dims(self.y[:, i], axis=1)
            yvar = np.expand_dims(self.yvar[:, i], axis=1)

            if specialTreatment:
                x, y, yvar = (
                    np.empty((0, x.shape[-1])),
                    np.empty((0, y.shape[-1])),
                    np.empty((0, y.shape[-1])),
                )

            # Surrogate

            print(f"~ Model for output: {outi}")

            GP = SURROGATEtools.surrogate_model(
                x,
                y,
                yvar,
                self.surrogate_parameters,
                bounds=self.bounds,
                output=outi,
                output_transformed=outi_transformed,
                avoidPoints=self.avoidPoints,
                dfT=self.dfT,
                surrogateOptions=surrogateOptions,
                FixedValue=FixedValue,
                fileTraining=fileTraining,
            )

            # Fitting
            GP.fit()

            self.GP["individual_models"][i] = GP

        # ------------------------------------------------------------------------------------------------------
        # Combine them in a ModelListGP (create one single with MV but do not fit)
        # ------------------------------------------------------------------------------------------------------

        print(f"~ MV model to initialize combination")

        self.GP["combined_model"] = SURROGATEtools.surrogate_model(
            self.x,
            self.y,
            self.yvar,
            self.surrogate_parameters,
            avoidPoints=self.avoidPoints,
            bounds=self.bounds,
            dfT=self.dfT,
            surrogateOptions=self.surrogateOptions,
        )

        models = ()
        for GP in self.GP["individual_models"]:
            models += (GP.gpmodel,)
        self.GP["combined_model"].gpmodel = BOTORCHtools.ModifiedModelListGP(*models)

        print(f"--> Fitting of all models took {IOtools.getTimeDifference(time1)}")

        """
		*********************************************************************************************************************
			Write info (tables out of modified DataTraining pickle)
		*********************************************************************************************************************
		"""

        max_num_variables = 20

        # Convert to tables
        for IncludeVariablesContain in self.stepSettings["storeDataSurrogates"]:
            name_file = "".join(IncludeVariablesContain)

            fileTabularData = f"{self.stepSettings['folderOutputs']}/DataTraining_{name_file}_table.dat"
            fileTabularDataError = f"{self.stepSettings['folderOutputs']}/DataTraining_{name_file}_tableErrors.dat"
            TabularData = BOgraphics.TabularData(
                [f"x_{i}" for i in range(max_num_variables)],
                ["y"],
                file=fileTabularData,
            )
            TabularDataStds = BOgraphics.TabularData(
                [f"x_{i}" for i in range(max_num_variables)],
                ["y"],
                file=fileTabularDataError,
            )
            (
                pointsAdded,
                TabularData,
                TabularDataStds,
                outputs,
            ) = SURROGATEtools.writeTabulars(
                fileTraining,
                TabularData,
                TabularDataStds,
                [],
                IncludeVariablesContain=IncludeVariablesContain,
            )
            TabularData.updateFile(source_interface=outputs)
            TabularDataStds.updateFile(source_interface=outputs)

        """
		*********************************************************************************************************************
			Postprocessing
		*********************************************************************************************************************
		"""

        # Test (if test could not be launched is likely because a singular matrix for Choleski decomposition)
        print("--> Launching tests to assure batch evaluation accuracy")
        TESTtools.testBatchCapabilities(self.GP["combined_model"])
        print("--> Launching tests to assure model combination accuracy")
        TESTtools.testCombinationCapabilities(
            self.GP["individual_models"], self.GP["combined_model"]
        )
        print("--> Launching tests evaluate accuracy on training set (absolute units)")
        self.GP["combined_model"].testTraining(printYN=False)

        txt_time = IOtools.getTimeDifference(time1)

        print(
            "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n"
        )

        if self.fileOutputs is not None:
            with open(self.fileOutputs, "a") as f:
                f.write(f" (took total of {txt_time})")

    def defineFunctions(self, lambdaSingleObjective):
        """
        I create this so that, upon reading a pickle, I re-call it. Otherwise, it is very heavy to store lambdas
        """

        self.evaluators = {"GP": self.GP["combined_model"]}

        # **************************************************************************************************
        # Objective (Multi-objective model -> single objective residual)
        # **************************************************************************************************

        # Build lambda function to pass to acquisition
        def residual(Y):
            return lambdaSingleObjective(Y)[2]

        self.evaluators["objective"] = botorch.acquisition.objective.GenericMCObjective(
            residual
        )

        # **************************************************************************************************
        # Acquisition functions (Maximization problem in MITIM)
        # **************************************************************************************************

        best_f = self.evaluators["objective"](
            self.evaluators["GP"].train_Y.unsqueeze(1)
        ).max()

        if self.acquisitionType == "posterior_mean":
            self.evaluators["acq_function"] = BOTORCHtools.PosteriorMean(
                self.evaluators["GP"].gpmodel, objective=self.evaluators["objective"]
            )

        elif self.acquisitionType == "ei_mc":
            self.evaluators[
                "acq_function"
            ] = botorch.acquisition.monte_carlo.qExpectedImprovement(
                self.evaluators["GP"].gpmodel,
                objective=self.evaluators["objective"],
                best_f=best_f,
            )

        elif self.acquisitionType == "logei_mc":
            self.evaluators[
                "acq_function"
            ] = botorch.acquisition.logei.qLogExpectedImprovement(
                self.evaluators["GP"].gpmodel,
                objective=self.evaluators["objective"],
                best_f=best_f,
            )

        elif self.acquisitionType == "logei":
            print("* Chosen an analytic acquisition, igoring objective", typeMsg="w")
            self.evaluators[
                "acq_function"
            ] = botorch.acquisition.analytic.LogExpectedImprovement(
                self.evaluators["GP"].gpmodel, best_f=best_f
            )

        # **************************************************************************************************
        # Quick function to return components (I need this for ROOT too, since I need the components)
        # **************************************************************************************************

        def residual_function(x, outputComponents=False):
            mean, _, _, _ = self.evaluators["GP"].predict(x)
            yOut_fun, yOut_cal, yOut = lambdaSingleObjective(mean)

            return (yOut, yOut_fun, yOut_cal, mean) if outputComponents else yOut

        self.evaluators["residual_function"] = residual_function

        # **************************************************************************************************
        # Selector (Takes x and residuals of optimized points, and provides the indices for organization)
        # **************************************************************************************************

        self.evaluators["lambdaSelect"] = lambda x, res: correctResidualForProximity(
            x,
            res,
            self.train_X[self.BOmetrics["overall"]["indBest"]],
            self.BOmetrics["overall"]["Residual"][self.BOmetrics["overall"]["indBest"]],
            self.favorProximityType,
        )

    def optimize(
        self,
        lambdaSingleObjective,
        position_best_so_far=-1,
        seed=0,
        forceAllPointsInBounds=False,
    ):
        """
        ***********************************************
        Update functions to be used during optimization
        ***********************************************
        """
        self.defineFunctions(lambdaSingleObjective)

        """
		***********************************************
		Peform optimization
		***********************************************
		"""

        if self.fileOutputs is not None:
            with open(self.fileOutputs, "a") as f:
                f.write("\n\n * Running optimization workflows to find next points...")

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~ Evaluate Adquisition
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        time1 = datetime.datetime.now()

        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("~~~~ Running optimization methods")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        print(
            f'\n~~ Maximization of "{self.acquisitionType}" acquisition using "{self.optimizers}" methods to find {self.best_points_sequence} points\n'
        )

        self.x_next, self.InfoOptimization = OPTtools.optAcq(
            stepSettings=self.stepSettings,
            evaluators=self.evaluators,
            StrategyOptions=self.StrategyOptions,
            best_points=int(self.best_points_sequence),
            optimization_sequence=self.optimizers.split("-"),
            it_number=self.currentIteration,
            position_best_so_far=position_best_so_far,
            seed=seed,
            forceAllPointsInBounds=forceAllPointsInBounds,
        )

        print(
            f"\n~~ Complete acquisition workflows found {self.x_next.shape[0]} points"
        )

        txt_time = IOtools.getTimeDifference(time1)

    def curate_outliers(self):
        # Remove outliers
        self.outliers = removeOutliers(
            self.x,
            self.y,
            self.yvar,
            stds_outside=self.surrogateOptions["stds_outside"],
            stds_outside_checker=self.surrogateOptions["stds_outside_checker"],
            alreadyAvoided=self.avoidPoints,
        )

        # Info
        if len(self.outliers) > 0:
            print(f"\t* OUTLIERS in positions: {self.outliers}. Adding to avoid points")

        try:
            self.avoidPoints.extend(self.outliers)
        except:
            self.avoidPoints = [
                int(i) for i in np.append(self.avoidPoints, self.outliers)
            ]

        if len(self.avoidPoints) > 0:
            print(f"\t ~~ Avoiding {len(self.avoidPoints)} points: ", self.avoidPoints)


def removeOutliers(
    x, y, yvar, stds_outside=5, stds_outside_checker=1, alreadyAvoided=[]
):
    """
    This routine finds outliers to remove
    """

    if stds_outside is not None:
        print(
            f"\t Checking outliers by +-{stds_outside}sigma from the rest (min number of {stds_outside_checker})"
        )

        avoidPoints = []
        for i in range(y.shape[0]):
            outlier = False
            for j in range(y.shape[1]):
                outlier_this = TESTtools.isOutlier(
                    y[i, j],
                    np.delete(y[:, j], [i], axis=0),
                    stds_outside=stds_outside,
                    stds_outside_checker=stds_outside_checker,
                )
                outlier = outlier or outlier_this

                if outlier_this:
                    print(f"\t Point #{i} is an outlier in position {j}: {y[i,j]:.5f}")

            if outlier and i not in alreadyAvoided:
                avoidPoints.append(i)

    else:
        avoidPoints = []

    return avoidPoints


def correctResidualForProximity(x, res, xBest, resBest, favorProximityType):
    what_is_already_good_improvement = (
        1e-2  # Improvement of 100x is already good enough
    )

    indeces_raw = torch.argsort(res, dim=0, descending=True)

    # Raw organized
    if favorProximityType == 0:
        indeces = indeces_raw

    # Special treatment
    if favorProximityType == 1:
        # Improvement in residual
        resn = res / resBest

        # If improvement in residual is better than what_is_already_good_improvement, clip it
        resn = resn.clip(what_is_already_good_improvement)

        # Normalized distance
        dn = MATHtools.calculateDistance(xBest, x) / (
            MATHtools.calculateDistance(xBest, x * 0.0)
        )

        # Add the distance just as a super small, for organizing
        resn -= dn * 1e-6

        indeces = torch.argsort(resn, dim=0)

    # Provide info
    if indeces[0] != indeces_raw[0]:
        print("\t* Selection of best point has accounted for proximity")

    return indeces
