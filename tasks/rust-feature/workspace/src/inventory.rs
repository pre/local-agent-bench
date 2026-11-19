use std::fmt;

use crate::quantity::Quantity;

/// The scheduling state of a node.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NodeState {
    /// The node accepts new jobs.
    Ready,
    /// The node runs its jobs but accepts no new jobs.
    Cordoned,
    /// The node does not answer.
    Down,
}

/// One node of the inventory. `cpu` and `memory` are the allocatable
/// resources, `used_cpu` and `used_memory` are the resources that running
/// jobs request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Node {
    pub name: String,
    pub state: NodeState,
    pub cpu: u32,
    pub memory: Quantity,
    pub used_cpu: u32,
    pub used_memory: Quantity,
}

/// The resources that a job requests.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Request {
    pub cpu: u32,
    pub memory: Quantity,
}

/// An error in an inventory file, with the line number (starting at 1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InventoryError {
    pub line: usize,
    pub msg: String,
}

impl fmt::Display for InventoryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.msg)
    }
}

impl std::error::Error for InventoryError {}

/// Reads an inventory. Each line that is not empty and is not a `#`
/// comment holds one node:
///
/// ```text
/// gpu-a01 state=ready cpu=96 memory=1536Gi used_cpu=40 used_memory=600Gi
/// ```
///
/// `state` and `cpu` and `memory` are necessary. `used_cpu` and
/// `used_memory` are zero if they are not given.
pub fn parse_inventory(text: &str) -> Result<Vec<Node>, InventoryError> {
    let mut nodes: Vec<Node> = Vec::new();
    for (idx, line) in text.lines().enumerate() {
        let line_no = idx + 1;
        let err = |msg: String| InventoryError { line: line_no, msg };

        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let mut fields = line.split_whitespace();
        let name = fields.next().unwrap_or_default().to_string();
        if nodes.iter().any(|n| n.name == name) {
            return Err(err(format!("duplicate node {name}")));
        }

        let mut state = None;
        let mut cpu = None;
        let mut memory = None;
        let mut used_cpu = 0;
        let mut used_memory = Quantity::ZERO;
        for field in fields {
            let (key, value) = field
                .split_once('=')
                .ok_or_else(|| err(format!("expected key=value, found {field:?}")))?;
            match key {
                "state" => state = Some(parse_state(value).map_err(err)?),
                "cpu" => cpu = Some(parse_cpu(value).map_err(err)?),
                "used_cpu" => used_cpu = parse_cpu(value).map_err(err)?,
                "memory" => memory = Some(value.parse::<Quantity>().map_err(|e| err(e.to_string()))?),
                "used_memory" => used_memory = value.parse::<Quantity>().map_err(|e| err(e.to_string()))?,
                _ => return Err(err(format!("unknown key {key:?}"))),
            }
        }

        nodes.push(Node {
            name,
            state: state.ok_or_else(|| err("missing state".to_string()))?,
            cpu: cpu.ok_or_else(|| err("missing cpu".to_string()))?,
            memory: memory.ok_or_else(|| err("missing memory".to_string()))?,
            used_cpu,
            used_memory,
        });
    }
    Ok(nodes)
}

fn parse_state(value: &str) -> Result<NodeState, String> {
    match value {
        "ready" => Ok(NodeState::Ready),
        "cordoned" => Ok(NodeState::Cordoned),
        "down" => Ok(NodeState::Down),
        _ => Err(format!("unknown state {value:?}")),
    }
}

fn parse_cpu(value: &str) -> Result<u32, String> {
    value
        .parse::<u32>()
        .map_err(|_| format!("invalid cpu count {value:?}"))
}
