use placer::{place, Node, NodeState, Quantity, Request};

const GI: u64 = 1 << 30;

fn node(name: &str, state: NodeState, cpu: u32, mem_gi: u64, used_cpu: u32, used_gi: u64) -> Node {
    Node {
        name: name.to_string(),
        state,
        cpu,
        memory: Quantity::from_bytes(mem_gi * GI),
        used_cpu,
        used_memory: Quantity::from_bytes(used_gi * GI),
    }
}

fn req(cpu: u32, mem_gi: u64) -> Request {
    Request { cpu, memory: Quantity::from_bytes(mem_gi * GI) }
}

fn placed<'a>(nodes: &'a [Node], request: Request) -> Option<&'a str> {
    place(nodes, &request).map(|n| n.name.as_str())
}

use NodeState::*;

#[test]
fn best_fit_by_memory() {
    let nodes = vec![
        node("a", Ready, 64, 512, 0, 0),
        node("b", Ready, 64, 512, 0, 300),
        node("c", Ready, 64, 512, 0, 100),
    ];
    assert_eq!(placed(&nodes, req(8, 100)), Some("b"));
    assert_eq!(placed(&nodes, req(8, 300)), Some("c"));
    assert_eq!(placed(&nodes, req(8, 450)), Some("a"));
}

#[test]
fn memory_left_after_placement_decides() {
    let nodes = vec![
        node("small", Ready, 16, 64, 0, 0),
        node("large", Ready, 128, 1024, 0, 900),
    ];
    // Both have room. "large" has 124Gi free and "small" has 64Gi free.
    assert_eq!(placed(&nodes, req(4, 32)), Some("small"));
    assert_eq!(placed(&nodes, req(4, 100)), Some("large"));
}

#[test]
fn exact_fit_is_a_candidate() {
    let nodes = vec![node("a", Ready, 32, 256, 24, 192), node("b", Ready, 64, 512, 0, 0)];
    assert_eq!(placed(&nodes, req(8, 64)), Some("a"));
    assert_eq!(placed(&nodes, req(9, 64)), Some("b"));
    assert_eq!(placed(&nodes, req(8, 65)), Some("b"));
}

#[test]
fn only_ready_nodes() {
    let nodes = vec![
        node("a", Cordoned, 64, 512, 0, 500),
        node("b", Down, 64, 512, 0, 500),
        node("c", Ready, 64, 512, 0, 0),
    ];
    assert_eq!(placed(&nodes, req(1, 1)), Some("c"));
    assert_eq!(placed(&nodes[..2], req(1, 1)), None);
}

#[test]
fn tie_on_memory_uses_cpu_then_name() {
    let nodes = vec![
        node("n3", Ready, 64, 512, 10, 256),
        node("n1", Ready, 64, 512, 30, 256),
        node("n2", Ready, 64, 512, 30, 256),
        node("n0", Ready, 64, 512, 0, 256),
    ];
    assert_eq!(placed(&nodes, req(4, 16)), Some("n1"));
    assert_eq!(placed(&nodes, req(40, 16)), Some("n3"));
    let same = vec![node("node-b", Ready, 8, 8, 0, 0), node("node-B", Ready, 8, 8, 0, 0), node("node-a", Ready, 8, 8, 0, 0)];
    assert_eq!(placed(&same, req(1, 1)), Some("node-B"));
}

#[test]
fn overcommitted_node_has_no_room() {
    let nodes = vec![
        node("over-mem", Ready, 64, 512, 0, 600),
        node("over-cpu", Ready, 64, 512, 70, 0),
        node("ok", Ready, 64, 512, 0, 0),
    ];
    assert_eq!(placed(&nodes, req(1, 1)), Some("ok"));
    assert_eq!(placed(&nodes, req(0, 0)), Some("over-mem"));
    assert_eq!(placed(&nodes[..2], req(1, 1)), None);
}

#[test]
fn no_candidate() {
    assert_eq!(placed(&[], req(1, 1)), None);
    let nodes = vec![node("a", Ready, 8, 16, 0, 0)];
    assert_eq!(placed(&nodes, req(9, 1)), None);
    assert_eq!(placed(&nodes, req(1, 17)), None);
}

#[test]
fn returns_reference_into_slice() {
    let nodes = vec![node("a", Ready, 8, 16, 0, 0), node("b", Ready, 8, 16, 0, 8)];
    let chosen = place(&nodes, &req(1, 1)).unwrap();
    assert!(std::ptr::eq(chosen, &nodes[1]));
}
