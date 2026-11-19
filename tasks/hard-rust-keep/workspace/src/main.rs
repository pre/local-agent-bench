//! keepr <snapshot-list> <policy-file>: prints the retention plan.

use std::process::ExitCode;

fn read(path: &str) -> Result<String, String> {
    std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
}

fn run(args: &[String]) -> Result<String, String> {
    let [list, policy] = args else {
        return Err("usage: keepr <snapshot-list> <policy-file>".into());
    };
    let snapshots = keepr::parse_snapshots(&read(list)?).map_err(|e| format!("{list}: {e}"))?;
    let policy = keepr::parse_policy(&read(policy)?).map_err(|e| format!("{policy}: {e}"))?;
    let plan = keepr::plan(&snapshots, &policy).map_err(|e| e.to_string())?;
    Ok(keepr::render(&plan, &snapshots, &policy))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("keepr: {e}");
            ExitCode::FAILURE
        }
    }
}
