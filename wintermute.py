#!/usr/bin/python

from args import parse_args_and_env
from db_storage import DbStorage
from handlers import handle_cmd, handle_ssh
from llms.llm_connection import get_llm_connection
from llm_with_state import LLMWithState
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from targets.target_manager import create_target_connection


# helper to fill the history table with data from the db
def get_history_table(config, run_id: int, db: DbStorage, round: int) -> Table:
    table = Table(title="Executed Command History", show_header=True, show_lines=True)
    table.add_column("ThinkTime", style="dim")
    table.add_column("Tokens", style="dim")
    table.add_column("Cmd")
    table.add_column("Resp. Size", justify="right")
    if config.enable_explanation:
        table.add_column("Explanation")
        table.add_column("ExplTime", style="dim")
        table.add_column("ExplTokens", style="dim")
    if config.enable_update_state:
        table.add_column("StateUpdTime", style="dim")
        table.add_column("StateUpdTokens", style="dim")

    for i in range(0, round+1):
        table.add_row(*db.get_round_data(run_id, i, config.enable_explanation, config.enable_update_state))

    return table

# setup infrastructure for outputing information
console = Console()

# parse arguments
config = parse_args_and_env(console)
console.log(config)

# setup in-memory/persistent storage for command history
db = DbStorage(config.log)
db.connect()
db.setup_db()

# create an identifier for this session/run
run_id = db.create_new_run(config)

# create the connection to the target
target = create_target_connection(config.target)

# setup the connection to the LLM server
llm_connection = get_llm_connection(config)

# instantiate the concrete LLM model
llm_gpt = LLMWithState(run_id, llm_connection, db, config)

# setup round meta-data
round : int = 0
gotRoot : bool = False

# and start everything up
while round < config.max_rounds and not gotRoot:

    console.log(f"[yellow]Starting round {round+1} of {config.max_rounds}")
    with console.status("[bold green]Asking LLM for a new command...") as status:
        answer = llm_gpt.get_next_cmd()

    with console.status("[bold green]Executing that command...") as status:
        if answer.result.startswith("test_credentials"):
            cmd, result, gotRoot = handle_ssh(config.target, answer.result)
        else:
            console.print(Panel(answer.result, title=f"[bold cyan]Got command from LLM:"))
            cmd, result, gotRoot = handle_cmd(target, answer.result)

    db.add_log_query(run_id, round, cmd, result, answer)
 
    # output the command and its result
    console.print(Panel(result, title=f"[bold cyan]{cmd}"))

    # analyze the result..
    if config.enable_explanation:
        with console.status("[bold green]Analyze its result...") as status:
            answer = llm_gpt.analyze_result(cmd, result)
            db.add_log_analyze_response(run_id, round, cmd, answer.result, answer)

    # .. and let our local model representation update its state
    if config.enable_update_state:
        # this must happen before the table output as we might include the
        # status processing time in the table..
        with console.status("[bold green]Updating fact list..") as status:
            state = llm_gpt.update_state(cmd, result)
            db.add_log_update_state(run_id, round, "", state.result, state)
    
    # Output Round Data
    console.print(get_history_table(config, run_id, db, round))

    if config.enable_update_state:
        console.print(Panel(llm_gpt.get_current_state(), title="What does the LLM Know about the system?"))

    # finish round and commit logs to storage
    db.commit()
    round += 1

# write the final result to the database and console
if gotRoot:
    db.run_was_success(run_id, round)
    console.print(Panel("[bold green]Got Root!", title="Run finished"))
else:
    db.run_was_failure(run_id, round)
    console.print(Panel("[green]maximum round number reached", title="Run finished"))
