"""Line-oriented alternative for terminal and screen-reader users."""
import argparse
import time

from .engine import AI_ID, HUMAN_ID, GameEngine
from .models import Direction, GameConfig, GameMode, GameStatus
from .strategies import STRATEGY_REGISTRY
from .worker import StrategyWorker


def describe(engine, board=False):
    lines = [f"Round {engine.rounds_completed} of {engine.config.move_limit}. Status: {engine.status.value}."]
    for name, snake in engine.snakes.items():
        lines.append(f"{name}: score {snake.score}, head {snake.body[0]}, direction {snake.direction.name.lower()}.")
        if board:
            lines.append(f"{name} body, head to tail: {snake.body}.")
    lines.append(f"Apples: {engine.apples}. Coordinates are (column, row), starting at zero at top left.")
    lines.append(f"Active turn: {engine.active_snake_id}.")
    if engine.status is GameStatus.FINISHED:
        lines.extend([engine.finish_reason, engine.error_message, f"Winner: {engine.winner_id or 'draw'}."])
    return "\n".join(line for line in lines if line)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Text-mode Snake. Decisions advance only on command; no timed input required.")
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--columns", type=int, default=20)
    parser.add_argument("--apples", type=int, default=5)
    parser.add_argument("--moves", type=int, default=200)
    parser.add_argument("--speed", type=int, default=4, help="Stored AI speed; text mode advances on command.")
    parser.add_argument("--mode", choices=["single", "versus"], default="single")
    parser.add_argument("--strategy", choices=list(STRATEGY_REGISTRY), default="Greedy")
    args = parser.parse_args(argv)
    try:
        config = GameConfig(rows=args.rows, columns=args.columns, apple_count=args.apples,
                            move_limit=args.moves, ai_speed=args.speed,
                            mode=GameMode.VERSUS if args.mode == "versus" else GameMode.SINGLE,
                            strategy_name=args.strategy)
    except ValueError as exc:
        parser.error(str(exc))
    engine = GameEngine(config)
    worker = None
    help_text = "Commands: status, board (all body coordinates), up/down/left/right, next (AI turn), restart, help, quit."
    print(help_text)
    print(describe(engine))
    try:
        while True:
            command = input("Command: ").strip().lower()
            if command in ("quit", "exit"):
                break
            if command == "help":
                print(help_text)
                continue
            if command == "restart":
                if worker:
                    worker.close()
                    worker = None
                engine = GameEngine(config)
            elif command in ("next", "up", "down", "left", "right") and engine.status is GameStatus.RUNNING:
                if engine.active_snake_id == HUMAN_ID:
                    if command == "next":
                        print("Choose up, down, left, or right for the human turn.")
                        continue
                    outcome = engine.step(HUMAN_ID, Direction[command.upper()])
                    if not outcome.accepted:
                        print(outcome.message)
                elif command != "next":
                    print("It is the AI turn. Use next.")
                    continue
                else:
                    try:
                        if worker is None:
                            worker = StrategyWorker(STRATEGY_REGISTRY[config.strategy_name], construct=True)
                        worker.submit(engine.snapshot(), AI_ID, engine.rng.getstate())
                        print("AI thinking.")
                        result = None
                        while result is None:
                            result = worker.poll()
                            time.sleep(0.01)
                        direction, state, error = result
                        if error:
                            raise RuntimeError(error)
                        outcome = engine.step(AI_ID, direction)
                        if not outcome.accepted:
                            raise ValueError(outcome.message)
                        engine.rng.setstate(state)
                    except Exception as exc:
                        engine.fail_strategy(AI_ID, f"{type(exc).__name__}: {exc}")
            elif command not in ("status", "board"):
                print(help_text)
            if engine.status is GameStatus.FINISHED and worker:
                worker.close()
                worker = None
            print(describe(engine, board=command == "board"))
    except (EOFError, KeyboardInterrupt):
        print("Session ended.")
    finally:
        if worker:
            worker.close()
