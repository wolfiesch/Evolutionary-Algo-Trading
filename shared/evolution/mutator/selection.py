"""
Selection operators for evolutionary strategy search.

Phase 2D: Tournament, elite, and roulette selection.
"""
import random
from typing import TypeVar, Generic

from shared.evolution.fitness import FitnessResult
from shared.evolution.mutator.generator import GeneratedStrategy


# Type alias for strategy-fitness pair
StrategyFitnessPair = tuple[GeneratedStrategy, FitnessResult]


def tournament_selection(
    population: list[StrategyFitnessPair],
    tournament_size: int = 3,
) -> GeneratedStrategy:
    """
    Select strategy via tournament selection.

    Randomly samples tournament_size individuals and returns the best.
    This provides selection pressure while maintaining diversity.

    Args:
        population: List of (strategy, fitness) pairs
        tournament_size: Number of contestants (default: 3)

    Returns:
        Best strategy from the tournament
    """
    if not population:
        raise ValueError("Population is empty")

    # Clamp tournament size to population size
    tournament_size = min(tournament_size, len(population))

    # Random sample
    contestants = random.sample(population, tournament_size)

    # Return best (highest fitness score)
    winner = max(contestants, key=lambda x: x[1].final_score)
    return winner[0]


def elite_selection(
    population: list[StrategyFitnessPair],
    elite_count: int = 2,
) -> list[GeneratedStrategy]:
    """
    Select top N strategies (elitism).

    Elite strategies survive unchanged to the next generation,
    preserving good solutions from being lost to mutation.

    Args:
        population: List of (strategy, fitness) pairs (must be sorted by fitness)
        elite_count: Number of elites to keep (default: 2)

    Returns:
        List of elite strategies (unchanged)
    """
    if not population:
        return []

    # Population should already be sorted, but ensure it
    sorted_pop = sorted(population, key=lambda x: x[1].final_score, reverse=True)

    # Take top N
    elite_count = min(elite_count, len(sorted_pop))
    return [strat for strat, _ in sorted_pop[:elite_count]]


def roulette_selection(
    population: list[StrategyFitnessPair],
) -> GeneratedStrategy:
    """
    Fitness-proportionate (roulette wheel) selection.

    Probability of selection is proportional to fitness score.
    Better strategies have higher chance of being selected.

    Args:
        population: List of (strategy, fitness) pairs

    Returns:
        Selected strategy

    Note:
        Handles negative and zero fitness by shifting scores to positive range.
    """
    if not population:
        raise ValueError("Population is empty")

    if len(population) == 1:
        return population[0][0]

    # Get all scores
    scores = [p[1].final_score for p in population]

    # Shift to positive range if needed
    min_score = min(scores)
    if min_score <= 0:
        # Shift all scores so minimum is 0.01 (avoid zero probability)
        shift = abs(min_score) + 0.01
        scores = [s + shift for s in scores]

    # Calculate total
    total = sum(scores)

    if total == 0:
        # All scores are zero - uniform random selection
        return random.choice(population)[0]

    # Spin the wheel
    spin = random.uniform(0, total)
    cumulative = 0

    for (strategy, fitness), score in zip(population, scores):
        cumulative += score
        if cumulative >= spin:
            return strategy

    # Fallback (shouldn't reach here)
    return population[-1][0]


def rank_selection(
    population: list[StrategyFitnessPair],
    selection_pressure: float = 1.5,
) -> GeneratedStrategy:
    """
    Rank-based selection.

    Selection probability based on rank, not raw fitness value.
    More robust to outliers and extreme fitness values.

    Args:
        population: List of (strategy, fitness) pairs
        selection_pressure: Higher = stronger preference for top ranks (default: 1.5)

    Returns:
        Selected strategy
    """
    if not population:
        raise ValueError("Population is empty")

    if len(population) == 1:
        return population[0][0]

    # Sort by fitness (worst to best)
    sorted_pop = sorted(population, key=lambda x: x[1].final_score)
    n = len(sorted_pop)

    # Linear ranking: worst gets rank 1, best gets rank n
    # Probability = (2 - SP + 2*(SP-1)*(rank-1)/(n-1)) / n
    # where SP = selection_pressure
    weights = []
    for i in range(n):
        rank = i + 1  # 1 to n
        if n > 1:
            weight = (2 - selection_pressure + 2 * (selection_pressure - 1) * (rank - 1) / (n - 1)) / n
        else:
            weight = 1.0
        weights.append(max(0.01, weight))  # Ensure positive

    # Normalize
    total = sum(weights)
    probs = [w / total for w in weights]

    # Select based on probabilities
    return random.choices(sorted_pop, weights=probs, k=1)[0][0]


def select_diverse_parents(
    population: list[StrategyFitnessPair],
    count: int = 2,
    method: str = "tournament",
    tournament_size: int = 3,
) -> list[GeneratedStrategy]:
    """
    Select multiple diverse parents for crossover.

    Ensures parents are different strategies (if possible).

    Args:
        population: List of (strategy, fitness) pairs
        count: Number of parents to select (default: 2)
        method: Selection method ("tournament", "roulette", "rank")
        tournament_size: Tournament size if using tournament selection

    Returns:
        List of selected strategies
    """
    if len(population) < count:
        # Not enough strategies - return what we have
        return [strat for strat, _ in population]

    parents: list[GeneratedStrategy] = []
    max_attempts = count * 3  # Avoid infinite loop
    attempts = 0

    while len(parents) < count and attempts < max_attempts:
        if method == "tournament":
            candidate = tournament_selection(population, tournament_size)
        elif method == "roulette":
            candidate = roulette_selection(population)
        elif method == "rank":
            candidate = rank_selection(population)
        else:
            candidate = tournament_selection(population, tournament_size)

        # Check if already selected (by name)
        if not any(p.name == candidate.name for p in parents):
            parents.append(candidate)

        attempts += 1

    # If couldn't find enough diverse parents, add duplicates
    while len(parents) < count:
        parents.append(tournament_selection(population, tournament_size))

    return parents
