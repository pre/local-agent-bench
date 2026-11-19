//! Command line tool of jobq.
//!
//!     jobq replay <trace-file>   run a trace and print the log
//!     jobq check <trace-file>    parse a trace and print the count of steps

use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (cmd, path) = match args.as_slice() {
        [cmd, path] if cmd == "replay" || cmd == "check" => (cmd.as_str(), path.as_str()),
        _ => {
            eprintln!("usage: jobq replay|check <trace-file>");
            return ExitCode::from(2);
        }
    };
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("jobq: {path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    let trace = match jobq::parse(&text) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("jobq: {path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    match cmd {
        "check" => println!("{} steps", trace.steps.len()),
        _ => print!("{}", jobq::replay(&trace)),
    }
    ExitCode::SUCCESS
}
