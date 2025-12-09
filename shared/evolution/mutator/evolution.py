"""
Evolution engine - main loop for LLM-driven strategy evolution.

Phase 2D: Full evolution with selection, crossover, mutation, and checkpointing.
"""
import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from shared.evolution.fitness import FitnessResult
from shared.evolution.mutator.generator import GeneratedStrategy, StrategyGenerator
from shared.evolution.mutator.crossover import CrossoverOperator
from shared.evolution.mutator.selection import (
    tournament_selection,
    elite_selection,
    select_diverse_parents,
)

logger = logging.getLogger(__name__)


@dataclass
class EvolutionConfig:
    """Configuration for evolution engine."""

    population_size: int = 10
    generations: int = 20
    elite_count: int = 2  # Strategies that survive unchanged
    mutation_rate: float = 0.7  # Probability of mutation vs crossover
    crossover_rate: float = 0.3  # Probability of crossover
    tournament_size: int = 3  # Tournament selection size
    min_diversity: float = 0.3  # Minimum population diversity
    max_stagnation: int = 5  # Generations without improvement before reset
    checkpoint_interval: int = 5  # Save checkpoint every N generations
    checkpoint_dir: Optional[str] = None  # Directory for checkpoints


@dataclass
class EvolutionState:
    """State that can be checkpointed and resumed."""

    generation: int = 0
    best_score: float = 0.0
    stagnation_count: int = 0
    population: list[dict] = field(default_factory=list)
    fitness_history: list[dict] = field(default_factory=list)
    diversity_history: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvolutionState":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class EvolutionResult:
    """Results from evolution run."""

    best_strategy: Optional[GeneratedStrategy]
    best_fitness: Optional[FitnessResult]
    final_population: list[tuple[GeneratedStrategy, FitnessResult]]
    generations_run: int
    fitness_history: list[dict]
    diversity_history: list[float]
    early_stopped: bool = False
    stop_reason: Optional[str] = None


# Type alias for strategy-fitness pair
StrategyFitnessPair = tuple[GeneratedStrategy, FitnessResult]

# Type alias for evaluation function
EvaluationFunc = Callable[[GeneratedStrategy], tuple[FitnessResult, dict]]


class EvolutionEngine:
    """
    Main evolution engine for LLM-driven strategy search.

    Features:
    - Tournament selection with elitism
    - LLM-guided mutation and crossover
    - Population diversity tracking
    - Checkpoint/resume capability
    - Stagnation detection and recovery

    Usage:
        engine = EvolutionEngine(
            config=EvolutionConfig(),
            generator=StrategyGenerator(llm_client),
            crossover=CrossoverOperator(llm_client),
            evaluator=my_eval_function,
        )

        result = engine.run(initial_population)
    """

    def __init__(
        self,
        config: EvolutionConfig,
        generator: StrategyGenerator,
        crossover: CrossoverOperator,
        evaluator: EvaluationFunc,
    ):
        """
        Initialize evolution engine.

        Args:
            config: Evolution configuration
            generator: Strategy generator for initial pop and mutations
            crossover: Crossover operator for combining strategies
            evaluator: Function that evaluates a strategy and returns (fitness, summary)
        """
        self.config = config
        self.generator = generator
        self.crossover = crossover
        self.evaluator = evaluator

        self.state = EvolutionState()
        self._population: list[StrategyFitnessPair] = []

    def run(
        self,
        initial_population: Optional[list[GeneratedStrategy]] = None,
        resume_from: Optional[str] = None,
    ) -> EvolutionResult:
        """
        Run the evolution loop.

        Args:
            initial_population: Initial strategies (if not resuming)
            resume_from: Path to checkpoint file to resume from

        Returns:
            EvolutionResult with best strategies and history
        """
        # Resume from checkpoint if specified
        if resume_from:
            self._load_checkpoint(resume_from)
            logger.info(f"Resumed from checkpoint at generation {self.state.generation}")
        elif initial_population:
            self._initialize_population(initial_population)
        else:
            raise ValueError("Must provide initial_population or resume_from")

        start_gen = self.state.generation
        target_gen = start_gen + self.config.generations

        logger.info(f"Starting evolution from gen {start_gen} to gen {target_gen}")
        logger.info(f"Population size: {len(self._population)}")

        # Main evolution loop
        while self.state.generation < target_gen:
            gen_start = time.time()
            self.state.generation += 1

            logger.info(f"\n{'=' * 60}")
            logger.info(f"GENERATION {self.state.generation}")
            logger.info("=" * 60)

            # Evolve to next generation
            self._evolve_generation()

            # Track diversity
            diversity = self._calculate_diversity()
            self.state.diversity_history.append(diversity)

            # Get best
            if self._population:
                best_strat, best_fitness = self._population[0]
                current_best = best_fitness.final_score

                # Track fitness history
                self.state.fitness_history.append({
                    "generation": self.state.generation,
                    "best_score": current_best,
                    "avg_score": self._avg_fitness(),
                    "diversity": diversity,
                    "timestamp": datetime.now().isoformat(),
                })

                # Check for improvement
                if current_best > self.state.best_score:
                    logger.info(f"New best! Score: {current_best:.3f} (was {self.state.best_score:.3f})")
                    self.state.best_score = current_best
                    self.state.stagnation_count = 0
                else:
                    self.state.stagnation_count += 1
                    logger.info(f"No improvement. Stagnation: {self.state.stagnation_count}/{self.config.max_stagnation}")

                # Log generation summary
                gen_time = time.time() - gen_start
                logger.info(f"Gen {self.state.generation}: Best={current_best:.3f}, "
                           f"Avg={self._avg_fitness():.3f}, Diversity={diversity:.2f}, "
                           f"Time={gen_time:.1f}s")

            # Check stagnation
            if self.state.stagnation_count >= self.config.max_stagnation:
                logger.warning("Stagnation detected! Injecting fresh strategies...")
                self._inject_fresh_strategies()
                self.state.stagnation_count = 0

            # Checkpoint
            if self.state.generation % self.config.checkpoint_interval == 0:
                self._save_checkpoint()

        # Final results
        return self._build_result(early_stopped=False)

    def _initialize_population(self, initial: list[GeneratedStrategy]):
        """Evaluate and sort initial population."""
        logger.info(f"Evaluating {len(initial)} initial strategies...")

        self._population = []
        for strat in initial:
            fitness, _ = self.evaluator(strat)
            self._population.append((strat, fitness))
            logger.info(f"  {strat.name}: Score={fitness.final_score:.3f}")

        # Sort by fitness (best first)
        self._population.sort(key=lambda x: x[1].final_score, reverse=True)

        # Initialize state
        if self._population:
            self.state.best_score = self._population[0][1].final_score
            self.state.fitness_history.append({
                "generation": 0,
                "best_score": self.state.best_score,
                "avg_score": self._avg_fitness(),
                "diversity": self._calculate_diversity(),
                "timestamp": datetime.now().isoformat(),
            })

    def _evolve_generation(self):
        """Evolve population to next generation."""
        if not self._population:
            return

        new_population: list[StrategyFitnessPair] = []

        # 1. Elite preservation - keep top N unchanged
        elites = elite_selection(self._population, self.config.elite_count)
        for elite in elites:
            # Find fitness for elite
            for strat, fitness in self._population:
                if strat.name == elite.name:
                    new_population.append((elite, fitness))
                    logger.info(f"Elite preserved: {elite.name} (Score: {fitness.final_score:.3f})")
                    break

        # 2. Fill remaining slots with offspring
        remaining = self.config.population_size - len(new_population)

        for _ in range(remaining):
            # Decide: mutation or crossover
            if random.random() < self.config.mutation_rate:
                # Mutation: select parent and mutate
                offspring = self._mutate()
            else:
                # Crossover: select two parents and combine
                offspring = self._crossover()

            if offspring:
                # Evaluate offspring
                fitness, _ = self.evaluator(offspring)
                new_population.append((offspring, fitness))

                status = "DISQUALIFIED" if fitness.disqualified else f"Score={fitness.final_score:.3f}"
                logger.info(f"Offspring: {offspring.name} - {status}")
            else:
                # Fallback: generate new random strategy
                logger.warning("Operator failed, generating fresh strategy...")
                fresh = self.generator.generate()
                if fresh:
                    fitness, _ = self.evaluator(fresh)
                    new_population.append((fresh, fitness))

        # Sort by fitness
        self._population = sorted(new_population, key=lambda x: x[1].final_score, reverse=True)

    def _mutate(self) -> Optional[GeneratedStrategy]:
        """Select a parent and mutate it."""
        # Tournament selection
        parent = tournament_selection(self._population, self.config.tournament_size)

        # Get parent's fitness
        parent_fitness = None
        for strat, fitness in self._population:
            if strat.name == parent.name:
                parent_fitness = fitness
                break

        if parent_fitness is None:
            return None

        # Mutate
        return self.generator.mutate(
            strategy=parent,
            sharpe=parent_fitness.sharpe_ratio,
            win_rate=parent_fitness.win_rate,
            max_dd=parent_fitness.max_drawdown,
            trade_count=parent_fitness.trade_count,
        )

    def _crossover(self) -> Optional[GeneratedStrategy]:
        """Select two parents and perform crossover."""
        # Select two different parents
        parents = select_diverse_parents(
            self._population,
            count=2,
            method="tournament",
            tournament_size=self.config.tournament_size,
        )

        if len(parents) < 2:
            return None

        # Get fitness for both parents
        fitness_a = fitness_b = None
        for strat, fitness in self._population:
            if strat.name == parents[0].name:
                fitness_a = fitness
            elif strat.name == parents[1].name:
                fitness_b = fitness

        if fitness_a is None or fitness_b is None:
            return None

        # Crossover
        return self.crossover.crossover(
            parent_a=parents[0],
            fitness_a=fitness_a,
            parent_b=parents[1],
            fitness_b=fitness_b,
        )

    def _inject_fresh_strategies(self):
        """Inject fresh strategies to escape local optima."""
        # Replace bottom half with fresh strategies
        inject_count = self.config.population_size // 2
        keep_count = self.config.population_size - inject_count

        # Keep top performers
        self._population = self._population[:keep_count]

        # Generate fresh strategies
        for _ in range(inject_count):
            fresh = self.generator.generate()
            if fresh:
                fitness, _ = self.evaluator(fresh)
                self._population.append((fresh, fitness))

        # Re-sort
        self._population.sort(key=lambda x: x[1].final_score, reverse=True)
        logger.info(f"Injected {inject_count} fresh strategies")

    def _calculate_diversity(self) -> float:
        """
        Calculate population diversity.

        Measures how different strategies are from each other.
        Returns value between 0 (all identical) and 1 (all unique).
        """
        if len(self._population) < 2:
            return 1.0

        # Use primitive-based diversity: count unique primitive sets
        primitive_sets = set()
        for strat, _ in self._population:
            # Extract primitives from entry and exit
            import re
            func_pattern = re.compile(r"(\w+)\([^)]*\)")
            entry_funcs = frozenset(func_pattern.findall(strat.entry_long))
            exit_funcs = frozenset(func_pattern.findall(strat.exit_long))
            primitive_sets.add((entry_funcs, exit_funcs))

        # Diversity = unique sets / total population
        return len(primitive_sets) / len(self._population)

    def _avg_fitness(self) -> float:
        """Calculate average fitness of non-disqualified strategies."""
        valid = [f.final_score for _, f in self._population if not f.disqualified]
        return sum(valid) / len(valid) if valid else 0.0

    def _save_checkpoint(self):
        """Save current state to checkpoint file."""
        if not self.config.checkpoint_dir:
            return

        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Serialize population
        self.state.population = [
            {
                "strategy": {
                    "name": s.name,
                    "entry_long": s.entry_long,
                    "exit_long": s.exit_long,
                    "rationale": s.rationale,
                    "mutation_type": s.mutation_type,
                    "mutation_description": s.mutation_description,
                },
                "fitness": {
                    "final_score": f.final_score,
                    "sharpe_ratio": f.sharpe_ratio,
                    "max_drawdown": f.max_drawdown,
                    "trade_count": f.trade_count,
                    "win_rate": f.win_rate,
                    "profit_factor": f.profit_factor,
                    "total_return": f.total_return,
                    "disqualified": f.disqualified,
                    "disqualification_reason": f.disqualification_reason,
                }
            }
            for s, f in self._population
        ]

        checkpoint_path = checkpoint_dir / f"checkpoint_gen{self.state.generation}.json"
        with open(checkpoint_path, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2)

        logger.info(f"Checkpoint saved: {checkpoint_path}")

    def _load_checkpoint(self, checkpoint_path: str):
        """Load state from checkpoint file."""
        with open(checkpoint_path, "r") as f:
            data = json.load(f)

        self.state = EvolutionState.from_dict(data)

        # Reconstruct population
        self._population = []
        for item in self.state.population:
            strat = GeneratedStrategy(
                name=item["strategy"]["name"],
                entry_long=item["strategy"]["entry_long"],
                exit_long=item["strategy"]["exit_long"],
                rationale=item["strategy"].get("rationale"),
                mutation_type=item["strategy"].get("mutation_type"),
                mutation_description=item["strategy"].get("mutation_description"),
            )
            fitness = FitnessResult(
                final_score=item["fitness"]["final_score"],
                sharpe_ratio=item["fitness"]["sharpe_ratio"],
                max_drawdown=item["fitness"]["max_drawdown"],
                trade_count=item["fitness"]["trade_count"],
                win_rate=item["fitness"]["win_rate"],
                profit_factor=item["fitness"]["profit_factor"],
                total_return=item["fitness"]["total_return"],
                disqualified=item["fitness"]["disqualified"],
                disqualification_reason=item["fitness"].get("disqualification_reason"),
            )
            self._population.append((strat, fitness))

    def _build_result(self, early_stopped: bool, stop_reason: str = None) -> EvolutionResult:
        """Build final result object."""
        best_strat = best_fitness = None
        if self._population:
            best_strat, best_fitness = self._population[0]

        return EvolutionResult(
            best_strategy=best_strat,
            best_fitness=best_fitness,
            final_population=self._population.copy(),
            generations_run=self.state.generation,
            fitness_history=self.state.fitness_history.copy(),
            diversity_history=self.state.diversity_history.copy(),
            early_stopped=early_stopped,
            stop_reason=stop_reason,
        )
