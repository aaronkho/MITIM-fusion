import profile
import numpy as np
from mitim_tools.misc_tools import MATHtools
from IPython import embed

def calculateGeometricFactors(profiles, n_theta=1001):

    # ----------------------------------------
    # Raw parameters from the file
    # 	in expro_util.f90, it performs those divisions to pass to geo library
    # ----------------------------------------

    r = profiles.profiles["rmin(m)"] / profiles.profiles["rmin(m)"][-1]
    R = profiles.profiles["rmaj(m)"] / profiles.profiles["rmin(m)"][-1]
    kappa = profiles.profiles["kappa(-)"]
    delta = profiles.profiles["delta(-)"]
    zeta = profiles.profiles["zeta(-)"]
    zmag = profiles.profiles["zmag(m)"] / profiles.profiles["rmin(m)"][-1]
    q = profiles.profiles["q(-)"]

    shape_coeffs = profiles.shape_cos+profiles.shape_sin

    # ----------------------------------------
    # Derivatives as defined in expro_util.f90
    # ----------------------------------------

    s_delta = r * MATHtools.deriv(r, delta)
    s_kappa = r / kappa * MATHtools.deriv(r, kappa)
    s_zeta = r * MATHtools.deriv(r, zeta)
    dzmag = MATHtools.deriv(r, zmag)
    dRmag = MATHtools.deriv(r, R)

    s_shape_coeffs = []
    for i in range(len(shape_coeffs)):
        if shape_coeffs[i] is not None:
            s_shape_coeffs.append(r * MATHtools.deriv(r, shape_coeffs[i]))
        else:
            s_shape_coeffs.append(None)

    # ----------------------------------------
    # Calculate the differencial volume at each radii
    # 	from f2py/geo/geo.f90 in gacode source we have geo_volume_prime.
    # ----------------------------------------

    geo_volume_prime = np.zeros(len(R))
    geo_surf = np.zeros(len(R))
    geo_fluxsurfave_grad_r = np.zeros(len(R))
    geo_bt0 = np.zeros(len(R))
    for j in range(len(R)):
        i = j - 1

        cos_sin = []
        cos_sin_s = []
        for k in range(len(shape_coeffs)):
            if shape_coeffs[k] is not None:
                cos_sin.append(shape_coeffs[k][i + 1])
                cos_sin_s.append(s_shape_coeffs[k][i + 1])
            else:
                cos_sin.append(None)
                cos_sin_s.append(None)

        (
            geo_volume_prime[i + 1],
            geo_surf[i + 1],
            geo_fluxsurfave_grad_r[i + 1],
            geo_bt0[i + 1],
        ) = volp_surf_Miller(
            R[i + 1],
            r[i + 1],
            delta[i + 1],
            kappa[i + 1],
            cos_sin,
            cos_sin_s,
            zeta[i + 1],
            zmag[i + 1],
            s_delta[i + 1],
            s_kappa[i + 1],
            s_zeta[i + 1],
            dzmag[i + 1],
            dRmag[i + 1],
            q[i + 1],
            n_theta=n_theta,
        )

    """
	from expro_util.f90 we have:
		expro_volp(i) = geo_volume_prime*r_min**2, where r_min = expro_rmin(expro_n_exp)
		expro_surf(i) = geo_surf*r_min**2
	"""

    volp = geo_volume_prime * profiles.profiles["rmin(m)"][-1] ** 2
    surf = geo_surf * profiles.profiles["rmin(m)"][-1] ** 2

    return volp, surf, geo_fluxsurfave_grad_r, geo_bt0


def volp_surf_Miller(
    geo_rmaj_in,
    geo_rmin_in,
    geo_delta_in,
    geo_kappa_in,
    cos_sin,
    cos_sin_s,
    geo_zeta_in,
    geo_zmag_in,
    geo_s_delta_in,
    geo_s_kappa_in,
    geo_s_zeta_in,
    geo_dzmag_in,
    geo_drmaj_in,
    geo_q_in,
    n_theta=1001,
):
    """
    Completety from f2py/geo/geo.f90
    """

    geo_rmin_in = geo_rmin_in.clip(
        1e-10
    )  # To avoid problems at 0 (Implemented by PRF, not sure how TGYRO deals with this)

    [
        geo_shape_cos0_in,
        geo_shape_cos1_in,
        geo_shape_cos2_in,
        geo_shape_cos3_in,
        geo_shape_cos4_in,
        geo_shape_cos5_in,
        geo_shape_cos6_in,
        _,
        _,
        _,
        geo_shape_sin3_in,
        geo_shape_sin4_in,
        geo_shape_sin5_in,
        geo_shape_sin6_in,
    ] = cos_sin

    [
        geo_shape_s_cos0_in,
        geo_shape_s_cos1_in,
        geo_shape_s_cos2_in,
        geo_shape_s_cos3_in,
        geo_shape_s_cos4_in,
        geo_shape_s_cos5_in,
        geo_shape_s_cos6_in,
        _,
        _,
        _,
        geo_shape_s_sin3_in,
        geo_shape_s_sin4_in,
        geo_shape_s_sin5_in,
        geo_shape_s_sin6_in,
    ] = cos_sin_s

    geo_signb_in = 1.0

    from numpy import arcsin as asin
    from numpy import cos as cos
    from numpy import sin as sin

    geov_theta = np.zeros(n_theta)
    geov_bigr = np.zeros(n_theta)
    geov_bigr_r = np.zeros(n_theta)
    geov_bigr_t = np.zeros(n_theta)
    bigz = np.zeros(n_theta)
    bigz_r = np.zeros(n_theta)
    bigz_t = np.zeros(n_theta)
    geov_jac_r = np.zeros(n_theta)
    geov_grad_r = np.zeros(n_theta)
    geov_l_t = np.zeros(n_theta)
    r_c = np.zeros(n_theta)
    bigz_l = np.zeros(n_theta)
    bigr_l = np.zeros(n_theta)
    geov_l_r = np.zeros(n_theta)
    geov_nsin = np.zeros(n_theta)

    pi_2 = 8.0 * np.arctan(1.0)
    d_theta = pi_2 / (n_theta - 1)

    for i in range(n_theta):
        #!-----------------------------------------
        #! Generalized Miller-type parameterization
        #!-----------------------------------------

        theta = -0.5 * pi_2 + (i - 1) * d_theta

        geov_theta[i] = theta

        x = asin(geo_delta_in)

        #! A
        #! dA/dtheta
        #! d^2A/dtheta^2
        a = (
            theta
            + geo_shape_cos0_in
            + geo_shape_cos1_in * cos(theta)
            + geo_shape_cos2_in * cos(2 * theta)
            + geo_shape_cos3_in * cos(3 * theta)
            + geo_shape_cos4_in * cos(4 * theta)
            + geo_shape_cos5_in * cos(5 * theta)
            + geo_shape_cos6_in * cos(6 * theta)
            + geo_shape_sin3_in * sin(3 * theta)
            + x * sin(theta)
            - geo_zeta_in * sin(2 * theta)
            + geo_shape_sin3_in * sin(3 * theta)
            + geo_shape_sin4_in * sin(4 * theta)
            + geo_shape_sin5_in * sin(5 * theta)
            + geo_shape_sin6_in * sin(6 * theta)
        )
        a_t = (
            1.0
            - geo_shape_cos1_in * sin(theta)
            - 2 * geo_shape_cos2_in * sin(2 * theta)
            - 3 * geo_shape_cos3_in * sin(3 * theta)
            - 4 * geo_shape_cos4_in * sin(4 * theta)
            - 5 * geo_shape_cos5_in * sin(5 * theta)
            - 6 * geo_shape_cos6_in * sin(6 * theta)
            + x * cos(theta)
            - 2 * geo_zeta_in * cos(2 * theta)
            + 3 * geo_shape_sin3_in * cos(3 * theta)
            + 4 * geo_shape_sin4_in * cos(4 * theta)
            + 5 * geo_shape_sin5_in * cos(5 * theta)
            + 6 * geo_shape_sin6_in * cos(6 * theta)
        )
        a_tt = (
            -geo_shape_cos1_in * cos(theta)
            - 4 * geo_shape_cos2_in * cos(2 * theta)
            - 9 * geo_shape_cos3_in * cos(3 * theta)
            - 16 * geo_shape_cos4_in * cos(4 * theta)
            - 25 * geo_shape_cos5_in * cos(5 * theta)
            - 36 * geo_shape_cos6_in * cos(6 * theta)
            - x * sin(theta)
            + 4 * geo_zeta_in * sin(2 * theta)
            - 9 * geo_shape_sin3_in * sin(3 * theta)
            - 16 * geo_shape_sin4_in * sin(4 * theta)
            - 25 * geo_shape_sin5_in * sin(5 * theta)
            - 36 * geo_shape_sin6_in * sin(6 * theta)
        )

        #! R(theta)
        #! dR/dr
        #! dR/dtheta
        #! d^2R/dtheta^2
        geov_bigr[i] = geo_rmaj_in + geo_rmin_in * cos(a)
        geov_bigr_r[i] = (
            geo_drmaj_in
            + cos(a)
            - sin(a)
            * (
                geo_shape_s_cos0_in
                + geo_shape_s_cos1_in * cos(theta)
                + geo_shape_s_cos2_in * cos(2 * theta)
                + geo_shape_s_cos3_in * cos(3 * theta)
                + geo_shape_s_cos4_in * cos(4 * theta)
                + geo_shape_s_cos5_in * cos(5 * theta)
                + geo_shape_s_cos6_in * cos(6 * theta)
                + geo_s_delta_in / cos(x) * sin(theta)
                - geo_s_zeta_in * sin(2 * theta)
                + geo_shape_s_sin3_in * sin(3 * theta)
                + geo_shape_s_sin4_in * sin(4 * theta)
                + geo_shape_s_sin5_in * sin(5 * theta)
                + geo_shape_s_sin6_in * sin(6 * theta)
            )
        )
        geov_bigr_t[i] = -geo_rmin_in * a_t * sin(a)
        bigr_tt = -geo_rmin_in * a_t**2 * cos(a) - geo_rmin_in * a_tt * sin(a)

        #!-----------------------------------------------------------

        #! A
        #! dA/dtheta
        #! d^2A/dtheta^2
        a = theta
        a_t = 1.0
        a_tt = 0.0

        #! Z(theta)
        #! dZ/dr
        #! dZ/dtheta
        #! d^2Z/dtheta^2
        bigz[i] = geo_zmag_in + geo_kappa_in * geo_rmin_in * sin(a)
        bigz_r[i] = geo_dzmag_in + geo_kappa_in * (1.0 + geo_s_kappa_in) * sin(a)
        bigz_t[i] = geo_kappa_in * geo_rmin_in * cos(a) * a_t
        bigz_tt = (
            -geo_kappa_in * geo_rmin_in * sin(a) * a_t**2
            + geo_kappa_in * geo_rmin_in * cos(a) * a_tt
        )

        g_tt = geov_bigr_t[i] ** 2 + bigz_t[i] ** 2

        geov_jac_r[i] = geov_bigr[i] * (
            geov_bigr_r[i] * bigz_t[i] - geov_bigr_t[i] * bigz_r[i]
        )

        geov_grad_r[i] = geov_bigr[i] * np.sqrt(g_tt) / geov_jac_r[i]

        geov_l_t[i] = np.sqrt(g_tt)

        r_c[i] = geov_l_t[i] ** 3 / (geov_bigr_t[i] * bigz_tt - bigz_t[i] * bigr_tt)

        bigz_l[i] = bigz_t[i] / geov_l_t[i]

        bigr_l[i] = geov_bigr_t[i] / geov_l_t[i]

        geov_l_r[i] = bigz_l[i] * bigz_r[i] + bigr_l[i] * geov_bigr_r[i]

        geov_nsin[i] = (
            geov_bigr_r[i] * geov_bigr_t[i] + bigz_r[i] * bigz_t[i]
        ) / geov_l_t[i]

    c = 0.0
    for i in range(n_theta):
        c = c + geov_l_t[i] / (geov_bigr[i] * geov_grad_r[i])

    f = geo_rmin_in / (c * d_theta / pi_2)

    c = 0.0
    for i in range(n_theta - 1):
        c = c + geov_l_t[i] * geov_bigr[i] / geov_grad_r[i]

    geo_volume_prime = pi_2 * c * d_theta

    # Line 716 in geo.f90
    geo_surf = 0.0
    for i in range(n_theta - 1):
        geo_surf = geo_surf + geov_l_t[i] * geov_bigr[i]
    geo_surf = pi_2 * geo_surf * d_theta

    # -----
    c = 0.0
    for i in range(n_theta - 1):
        c = c + geov_l_t[i] / (geov_bigr[i] * geov_grad_r[i])
    f = geo_rmin_in / (c * d_theta / pi_2)

    geov_b = np.zeros(n_theta)
    geov_g_theta = np.zeros(n_theta)
    geov_bt = np.zeros(n_theta)
    for i in range(n_theta):
        geov_bt[i] = f / geov_bigr[i]
        geov_bp = (geo_rmin_in / geo_q_in) * geov_grad_r[i] / geov_bigr[i]

        geov_b[i] = geo_signb_in * (geov_bt[i] ** 2 + geov_bp**2) ** 0.5
        geov_g_theta[i] = (
            geov_bigr[i]
            * geov_b[i]
            * geov_l_t[i]
            / (geo_rmin_in * geo_rmaj_in * geov_grad_r[i])
        )

    theta_0 = 0
    dx = geov_theta[1] - geov_theta[0]
    x0 = theta_0 - geov_theta[0]
    i1 = int(x0 / dx) + 1
    i2 = i1 + 1
    x1 = (i1 - 1) * dx
    z = (x0 - x1) / dx
    if i2 == n_theta:
        i2 -= 1
    geo_bt0 = geov_bt[i1] + (geov_bt[i2] - geov_bt[i1]) * z

    denom = 0
    for i in range(n_theta - 1):
        denom = denom + geov_g_theta[i] / geov_b[i]

    geo_fluxsurfave_grad_r = 0
    for i in range(n_theta - 1):
        geo_fluxsurfave_grad_r = (
            geo_fluxsurfave_grad_r
            + geov_grad_r[i] * geov_g_theta[i] / geov_b[i] / denom
        )

    return geo_volume_prime, geo_surf, geo_fluxsurfave_grad_r, geo_bt0
