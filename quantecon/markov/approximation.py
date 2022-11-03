"""
tauchen
-------
Discretizes Gaussian linear AR(1) processes via Tauchen's method

"""

from math import erfc, sqrt
from .core import MarkovChain
from quantecon import matrix_eqn as qme

import numpy as np
import scipy as sp
from numba import njit


def rouwenhorst(n, ybar, sigma, rho):
    r"""
    Takes as inputs n, p, q, psi. It will then construct a markov chain
    that estimates an AR(1) process of:
    :math:`y_t = \bar{y} + \rho y_{t-1} + \varepsilon_t`
    where :math:`\varepsilon_t` is i.i.d. normal of mean 0, std dev of sigma

    The Rouwenhorst approximation uses the following recursive defintion
    for approximating a distribution:

    .. math::

        \theta_2 =
        \begin{bmatrix}
        p     &  1 - p \\
        1 - q &  q     \\
        \end{bmatrix}

    .. math::

        \theta_{n+1} =
        p
        \begin{bmatrix}
        \theta_n & 0   \\
        0        & 0   \\
        \end{bmatrix}
        + (1 - p)
        \begin{bmatrix}
        0  & \theta_n  \\
        0  &  0        \\
        \end{bmatrix}
        + q
        \begin{bmatrix}
        0        & 0   \\
        \theta_n & 0   \\
        \end{bmatrix}
        + (1 - q)
        \begin{bmatrix}
        0  &  0        \\
        0  & \theta_n  \\
        \end{bmatrix}


    Parameters
    ----------
    n : int
        The number of points to approximate the distribution

    ybar : float
        The value :math:`\bar{y}` in the process.  Note that the mean of this
        AR(1) process, :math:`y`, is simply :math:`\bar{y}/(1 - \rho)`

    sigma : float
        The value of the standard deviation of the :math:`\varepsilon` process

    rho : float
        By default this will be 0, but if you are approximating an AR(1)
        process then this is the autocorrelation across periods

    Returns
    -------

    mc : MarkovChain
        An instance of the MarkovChain class that stores the transition
        matrix and state values returned by the discretization method

    """

    # Get the standard deviation of y
    y_sd = sqrt(sigma**2 / (1 - rho**2))

    # Given the moments of our process we can find the right values
    # for p, q, psi because there are analytical solutions as shown in
    # Gianluca Violante's notes on computational methods
    p = (1 + rho) / 2
    q = p
    psi = y_sd * np.sqrt(n - 1)

    # Find the states
    ubar = psi
    lbar = -ubar

    bar = np.linspace(lbar, ubar, n)

    def row_build_mat(n, p, q):
        """
        This method uses the values of p and q to build the transition
        matrix for the rouwenhorst method

        """

        if n == 2:
            theta = np.array([[p, 1 - p], [1 - q, q]])

        elif n > 2:
            p1 = np.zeros((n, n))
            p2 = np.zeros((n, n))
            p3 = np.zeros((n, n))
            p4 = np.zeros((n, n))

            new_mat = row_build_mat(n - 1, p, q)

            p1[:n - 1, :n - 1] = p * new_mat
            p2[:n - 1, 1:] = (1 - p) * new_mat
            p3[1:, :-1] = (1 - q) * new_mat
            p4[1:, 1:] = q * new_mat

            theta = p1 + p2 + p3 + p4
            theta[1:n - 1, :] = theta[1:n - 1, :] / 2

        else:
            raise ValueError("The number of states must be positive " +
                             "and greater than or equal to 2")

        return theta

    theta = row_build_mat(n, p, q)

    bar += ybar / (1 - rho)

    return MarkovChain(theta, bar)


def tauchen(rho, sigma_u, b=0., m=3, n=7):
    r"""
    Computes a Markov chain associated with a discretized version of
    the linear Gaussian AR(1) process

    .. math::

        y_{t+1} = b + \rho y_t + u_{t+1}

    using Tauchen's method. Here :math:`{u_t}` is an i.i.d. Gaussian process
    with zero mean.

    Parameters
    ----------
    b : scalar(float)
        The constant term of {y_t}
    rho : scalar(float)
        The autocorrelation coefficient
    sigma_u : scalar(float)
        The standard deviation of the random process
    m : scalar(int), optional(default=3)
        The number of standard deviations to approximate out to
    n : scalar(int), optional(default=7)
        The number of states to use in the approximation

    Returns
    -------

    mc : MarkovChain
        An instance of the MarkovChain class that stores the transition
        matrix and state values returned by the discretization method

    """

    # standard deviation of demeaned y_t
    std_y = np.sqrt(sigma_u**2 / (1 - rho**2))

    # top of discrete state space for demeaned y_t
    x_max = m * std_y

    # bottom of discrete state space for demeaned y_t
    x_min = -x_max

    # discretized state space for demeaned y_t
    x = np.linspace(x_min, x_max, n)

    step = (x_max - x_min) / (n - 1)
    half_step = 0.5 * step
    P = np.empty((n, n))

    # approximate Markov transition matrix for
    # demeaned y_t
    _fill_tauchen(x, P, n, rho, sigma_u, half_step)

    # shifts the state values by the long run mean of y_t
    mu = b / (1 - rho)

    mc = MarkovChain(P, state_values=x+mu)

    return mc


@njit
def std_norm_cdf(x):
    return 0.5 * erfc(-x / sqrt(2))


@njit
def _fill_tauchen(x, P, n, rho, sigma, half_step):
    for i in range(n):
        P[i, 0] = std_norm_cdf((x[0] - rho * x[i] + half_step) / sigma)
        P[i, n - 1] = 1 - \
            std_norm_cdf((x[n - 1] - rho * x[i] - half_step) / sigma)
        for j in range(1, n - 1):
            z = x[j] - rho * x[i]
            P[i, j] = (std_norm_cdf((z + half_step) / sigma) -
                       std_norm_cdf((z - half_step) / sigma))


def cartesian_product(arrays, row_major=True):
    """
    Create a Cartesian product from the list of grids in `arrays` and then
    flatten it so that S[i, :] is an array of grid points corresponding to
    state i.

    If row_major is True, then the Cartesian product of the grids is
    enumerated in row major order. Otherwise it is enumerated in column major.

    Currently the column major operation is copied from MATLAB and could
    surely be made more efficient.
    """

    m = len(arrays)
    if row_major:
        s = np.stack(np.meshgrid(*arrays, indexing='ij'), axis=-1)
        S = np.reshape(s, (-1, m))
    else:
        V = arrays
        gs = [len(v) for v in V]
        n = np.prod(gs)
        S = np.zeros((n, m))   # Discrete state space

        for i in range(m):
            if i == 0:
                S0 = np.ravel(V[i])
                S[:, i] = np.ravel(np.tile(S0, [np.prod(gs[i+1:]), 1]))
            else:
                S0 = np.sort(np.ravel(np.tile(V[i], [np.prod(gs[0:i]), 1])))
                S[:, i] = np.ravel(np.tile(S0, [np.prod(gs[i+1:]), 1]))
    return S


def discrete_var(A,
                 Omega,
                 grid_sizes=None,
                 std_devs=np.sqrt(10),
                 seed=1234,
                 sim_length=1_000_000,
                 burn_in=100_000,
                 row_major=True,
                 return_sim=False):
    r"""
    This code discretizes a VAR(1) process of the form:

    .. math::

        x_t = A x_{t-1} + u_t

    where :math:`{u_t}` is zero-mean Gaussian with variance-covariance
    matrix Omega.

    By default, the code removes the states that are never visited under the
    simulation that computes the transition probabilities.

    For a mathematical derivation check *Finite-State Approximation Of
    VAR Processes:  A Simulation Approach* by Stephanie Schmitt-Grohé and
    Martín Uribe, July 11, 2010.

    This code was adapted by Carlos Rondón-Moreno from Schmitt-Grohé and
    Uribe's code for MATLAB.

    Parameters
    ----------
    A : array_like(float)
        An m x m matrix containing the process' autocorrelation parameters
    Omega : array_like(float)
        An m x m variance-covariance matrix
    grid_sizes : array_like(int) or None
        An m-vector containing the number of grid points in the discretization
        of each dimension of x_t. If grid_sizes is None, then grid_sizes is
        set to (10, ..., 10).
    std_devs : float
        The number of standard deviations the grid should stretch in each
        dimension, where standard deviations are measured under the stationary
        distribution.
    sim_length : int
        The the length of the simulated time series (default,  1_000_000).
    burn_in : int
        The number of burn-in draws from the simulated series (default,
        100_000).
    row_major : bool
        If True then return form the cartesian product state grid using row
        major ordering.  Otherwise use column major.
    return_sim : bool
        If True then return the state space simulation generated by the model.

    Returns
    -------
    Pi : array_like(float)
        A square matrix containing the transition probability
        matrix of the discretized state.
    S : array_like(float)
        An array where element (i,j) of S is the discretized
        value of the j-th element of x_t in state i. Reducing S to its
        unique values yields the grid values.
    Xvec : array_like(float)
        A matrix of size m x sim_length containing the simulated time
        series of the m discretized states.


    Notes
    -----
        The code presently assumes normal shocks but normality is not required
        for the algorithm to work. The draws from the multivariate standard
        normal generator can be replaced by any other random number generator
        with mean 0 and unit standard deviation.


    Example
    -------

        This example discretizes the stochastic process used to calibrate
        the economic model included in ``Downward Nominal Wage Rigidity,
        Currency Pegs, and Involuntary Unemployment'' by Stephanie
        Schmitt-Grohé and Martín Uribe, Journal of Political Economy 124,
        October 2016, 1466-1514.

            A     = np.array([[0.7901, -1.3570],
                              [-0.0104, 0.8638]])
            Omega = np.array([[0.0012346, -0.0000776],
                              [-0.0000776, 0.0000401]])
            grid_sizes = np.array([21, 11])
            Pi, Xvec, S = discrete_var(A, Omega, grid_sizes,
                              sim_length=1_000_000, burn_in = 100_000)
    """

    m = len(A)   # The number of dimensions of the original state x_t
    default_grid_size = 10

    if grid_sizes is None:
        # Set the size of every grid to default_grid_size
        grid_sizes = np.full(m, default_grid_size)

    n = grid_sizes.prod()  # Size of the discretized state

    # Compute stationary variance-covariance matrix of AR process and use
    # it to obtain grid bounds.
    Sigma = qme.solve_discrete_lyapunov(A, Omega)
    sigma_vector = np.sqrt(np.diagonal(Sigma))    # Stationary std dev
    upper_bounds = std_devs * sigma_vector

    # Build the individual grids along each dimension
    V = []
    for i in range(m):
        b = np.linspace(-upper_bounds[i], upper_bounds[i], grid_sizes[i])
        V.append(b)

    S = cartesian_product(V, row_major=row_major)

    Pi = np.zeros((n, n))
    Xvec = np.zeros((m, sim_length))
    C = sp.linalg.sqrtm(Omega)

    # Run simulation to compute transition probabilities
    _run_sim(A, C, Pi, Xvec, S, sim_length, burn_in, seed)

    # Cut states where the column sum of Pi is zero (i.e., inaccesible states
    # according to the simulation)
    indx = np.where(np.sum(Pi, axis=0) > 0)
    Pi = Pi[indx[0], :]
    Pi = Pi[:, indx[0]]
    S  = S[indx[0], :]

    # Normalize
    sum_row = np.sum(Pi, axis=1)
    for i in range(len(Pi)):
        Pi[i, :] = Pi[i, :] / sum_row[i]

    if return_sim:
        return Pi, S, Xvec
    return Pi, S


@njit
def _run_sim(A, C, Pi, Xvec, S, sim_length, burn_in, seed):
    m = len(A)
    np.random.seed(seed)
    x0 = np.zeros((m, 1))
    d = np.sum(S**2, axis=1)
    ind_i = np.argmin(d)

    for t in range(sim_length + burn_in):
        # Update state
        drw = C @ np.random.randn(m, 1)
        x = A @ x0 + drw
        # Find the index of the state closest to x
        xx = np.reshape(x, (1, m))
        d = np.sum((S - xx)**2, axis=1)
        ind_j = np.argmin(d)

        if t > burn_in:
            Pi[ind_i, ind_j] += 1
            Xvec[:, t-burn_in] = x.T
        x0 = x
        ind_i = ind_j
