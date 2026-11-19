use std::process::ExitCode;

fn main() -> ExitCode {
    let Some(path) = std::env::args().nth(1) else {
        eprintln!("usage: agentconf <file>");
        return ExitCode::from(2);
    };
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(e) => {
            eprintln!("agentconf: {path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    match agentconf::parse(&text) {
        Ok(config) => {
            for key in config.keys() {
                println!("{key} = {}", config.get(key).unwrap());
            }
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("agentconf: {path}: {e}");
            ExitCode::FAILURE
        }
    }
}
