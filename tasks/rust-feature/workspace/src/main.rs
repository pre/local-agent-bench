use std::process::ExitCode;

use placer::{parse_inventory, place, Quantity, Request};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 4 {
        eprintln!("usage: placer <inventory-file> <cpu> <memory>");
        return ExitCode::from(2);
    }
    match run(&args[1], &args[2], &args[3]) {
        Ok(Some(name)) => {
            println!("{name}");
            ExitCode::SUCCESS
        }
        Ok(None) => {
            eprintln!("placer: no node has room for the job");
            ExitCode::from(3)
        }
        Err(msg) => {
            eprintln!("placer: {msg}");
            ExitCode::FAILURE
        }
    }
}

fn run(path: &str, cpu: &str, memory: &str) -> Result<Option<String>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
    let nodes = parse_inventory(&text).map_err(|e| format!("{path}: {e}"))?;
    let request = Request {
        cpu: cpu.parse().map_err(|_| format!("invalid cpu count {cpu:?}"))?,
        memory: memory.parse::<Quantity>().map_err(|e| e.to_string())?,
    };
    Ok(place(&nodes, &request).map(|node| node.name.clone()))
}
