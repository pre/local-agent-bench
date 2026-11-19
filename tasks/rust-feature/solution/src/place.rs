use crate::inventory::{Node, NodeState, Request};

/// Selects the node for a job. See the placement rules in the crate
/// documentation.
pub fn place<'a>(nodes: &'a [Node], request: &Request) -> Option<&'a Node> {
    nodes
        .iter()
        .filter(|node| node.state == NodeState::Ready)
        .filter_map(|node| {
            let free_cpu = node.cpu.saturating_sub(node.used_cpu);
            let free_memory = node.memory.saturating_sub(node.used_memory);
            if free_cpu < request.cpu || free_memory < request.memory {
                return None;
            }
            let left_memory = free_memory.bytes() - request.memory.bytes();
            let left_cpu = free_cpu - request.cpu;
            Some(((left_memory, left_cpu, node.name.as_str()), node))
        })
        .min_by(|a, b| a.0.cmp(&b.0))
        .map(|(_, node)| node)
}
