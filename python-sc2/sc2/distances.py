from sc2.position import Point2
from sc2.unit import Unit
from sc2.units import Units
from sc2.game_state import GameState

import logging

logger = logging.getLogger(__name__)

import math
from math import pow
import numpy as np
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from scipy.spatial.distance import pdist, cdist

from typing import Dict, Tuple, Iterable, Generator


class DistanceCalculation:
    def __init__(self):
        self.state: GameState = None
        # self._generated_frame = -100
        self._generated_frame2 = -100
        # Pdist condensed vector generated by scipy pdist, half the size of the cdist matrix as 1d array
        self._cached_pdist: np.ndarray = None
        self._cached_cdist: np.ndarray = None

    @property
    def _units_count(self) -> int:
        return len(self.all_units)

    @property
    def _pdist(self) -> np.ndarray:
        """ As property, so it will be recalculated each time it is called, or return from cache if it is called multiple times in teh same game_loop. """
        if self._generated_frame2 != self.state.game_loop:
            return self.calculate_distances()
        return self._cached_pdist

    @property
    def _cdist(self) -> np.ndarray:
        """ As property, so it will be recalculated each time it is called, or return from cache if it is called multiple times in teh same game_loop. """
        if self._generated_frame2 != self.state.game_loop:
            return self.calculate_distances()
        return self._cached_cdist

    def _calculate_distances_method1(self) -> np.ndarray:
        self._generated_frame2 = self.state.game_loop
        # Converts tuple [(1, 2), (3, 4)] to flat list like [1, 2, 3, 4]
        flat_positions = (coord for unit in self.all_units for coord in unit.position_tuple)
        # Converts to numpy array, then converts the flat array back to shape (n, 2): [[1, 2], [3, 4]]
        positions_array: np.ndarray = np.fromiter(flat_positions, dtype=np.float, count=2 * self._units_count).reshape(
            (self._units_count, 2)
        )
        assert len(positions_array) == self._units_count
        # See performance benchmarks
        self._cached_pdist = pdist(positions_array, "sqeuclidean")

        return self._cached_pdist

    def _calculate_distances_method2(self) -> np.ndarray:
        self._generated_frame2 = self.state.game_loop
        # Converts tuple [(1, 2), (3, 4)] to flat list like [1, 2, 3, 4]
        flat_positions = (coord for unit in self.all_units for coord in unit.position_tuple)
        # Converts to numpy array, then converts the flat array back to shape (n, 2): [[1, 2], [3, 4]]
        positions_array: np.ndarray = np.fromiter(flat_positions, dtype=np.float, count=2 * self._units_count).reshape(
            (self._units_count, 2)
        )
        assert len(positions_array) == self._units_count
        # See performance benchmarks
        self._cached_cdist = cdist(positions_array, positions_array, "sqeuclidean")

        return self._cached_cdist

    def _calculate_distances_method3(self) -> np.ndarray:
        """ Nearly same as above, but without asserts"""
        self._generated_frame2 = self.state.game_loop
        flat_positions = (coord for unit in self.all_units for coord in unit.position_tuple)
        positions_array: np.ndarray = np.fromiter(flat_positions, dtype=np.float, count=2 * self._units_count).reshape(
            (-1, 2)
        )
        # See performance benchmarks
        self._cached_cdist = cdist(positions_array, positions_array, "sqeuclidean")

        return self._cached_cdist

    # Helper functions

    def square_to_condensed(self, i, j) -> int:
        # Converts indices of a square matrix to condensed matrix
        # https://stackoverflow.com/a/36867493/10882657
        assert i != j, "No diagonal elements in condensed matrix! Diagonal elements are zero"
        if i < j:
            i, j = j, i
        return self._units_count * j - j * (j + 1) // 2 + i - 1 - j

    def convert_tuple_to_numpy_array(self, pos: Tuple[float, float]) -> np.ndarray:
        """ Converts a single position to a 2d numpy array with 1 row and 2 columns. """
        return np.fromiter(pos, dtype=float, count=2).reshape((1, 2))

    # Fast and simple calculation functions

    def distance_math_hypot(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def distance_math_hypot_squared(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        return pow(p1[0] - p2[0], 2) + pow(p1[1] - p2[1], 2)

    def _distance_squared_unit_to_unit_method0(self, unit1: Unit, unit2: Unit) -> float:
        return self.distance_math_hypot_squared(unit1.position_tuple, unit2.position_tuple)

    # Distance calculation using the pre-calculated matrix above

    def _distance_squared_unit_to_unit_method1(self, unit1: Unit, unit2: Unit) -> float:
        # If checked on units if they have the same tag, return distance 0 as these are not in the 1 dimensional pdist array - would result in an error otherwise
        if unit1.tag == unit2.tag:
            return 0
        # Calculate index, needs to be after pdist has been calculated and cached
        condensed_index = self.square_to_condensed(unit1.distance_calculation_index, unit2.distance_calculation_index)
        assert condensed_index < len(
            self._cached_pdist
        ), f"Condensed index is larger than amount of calculated distances: {condensed_index} < {len(self._cached_pdist)}, units that caused the assert error: {unit1} and {unit2}"
        distance = self._pdist[condensed_index]
        return distance

    def _distance_squared_unit_to_unit_method2(self, unit1: Unit, unit2: Unit) -> float:
        # Calculate index, needs to be after cdist has been calculated and cached
        return self._cdist[unit1.distance_calculation_index, unit2.distance_calculation_index]

    # Distance calculation using the fastest distance calculation functions

    def _distance_pos_to_pos(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        return self.distance_math_hypot(pos1, pos2)

    def _distance_units_to_pos(self, units: Units, pos: Tuple[float, float]) -> Generator[float, None, None]:
        """ This function does not scale well, if len(units) > 100 it gets fairly slow """
        return (self.distance_math_hypot(u.position_tuple, pos) for u in units)

    def _distance_unit_to_points(
        self, unit: Unit, points: Iterable[Tuple[float, float]]
    ) -> Generator[float, None, None]:
        """ This function does not scale well, if len(points) > 100 it gets fairly slow """
        pos = unit.position_tuple
        return (self.distance_math_hypot(p, pos) for p in points)

    def _distances_override_functions(self, method: int = 0):
        """ Overrides the internal distance calculation functions at game start in bot_ai.py self._prepare_start() function
        method 0: Use python's math.hypot
        The following methods calculate the distances between all units once:
        method 1: Use scipy's pdist condensed matrix (1d array)
        method 2: Use scipy's cidst square matrix (2d array)
        method 3: Use scipy's cidst square matrix (2d array) without asserts (careful: very weird error messages, but maybe slightly faster) """
        assert 0 <= method <= 3, f"Selected method was: {method}"
        if method == 0:
            self._distance_squared_unit_to_unit = self._distance_squared_unit_to_unit_method0
        elif method == 1:
            self._distance_squared_unit_to_unit = self._distance_squared_unit_to_unit_method1
            self.calculate_distances = self._calculate_distances_method1
        elif method == 2:
            self._distance_squared_unit_to_unit = self._distance_squared_unit_to_unit_method2
            self.calculate_distances = self._calculate_distances_method2
        elif method == 3:
            self._distance_squared_unit_to_unit = self._distance_squared_unit_to_unit_method2
            self.calculate_distances = self._calculate_distances_method3
