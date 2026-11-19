use placer::{parse_inventory, NodeState, Quantity};

const GI: u64 = 1 << 30;

#[test]
fn reads_nodes() {
    let text = "# comment\n\ngpu-a01 state=ready cpu=96 memory=1536Gi used_cpu=40 used_memory=600Gi\ncpu-b03 state=down cpu=128 memory=512Gi\n";
    let nodes = parse_inventory(text).unwrap();
    assert_eq!(nodes.len(), 2);
    assert_eq!(nodes[0].name, "gpu-a01");
    assert_eq!(nodes[0].state, NodeState::Ready);
    assert_eq!(nodes[0].cpu, 96);
    assert_eq!(nodes[0].memory, Quantity::from_bytes(1536 * GI));
    assert_eq!(nodes[0].used_cpu, 40);
    assert_eq!(nodes[0].used_memory, Quantity::from_bytes(600 * GI));
    assert_eq!(nodes[1].state, NodeState::Down);
    assert_eq!(nodes[1].used_memory, Quantity::ZERO);
}

#[test]
fn inventory_errors() {
    assert_eq!(parse_inventory("a state=ready cpu=1\n").unwrap_err().line, 1);
    assert_eq!(parse_inventory("a state=ready cpu=1 memory=1Gi\na state=ready cpu=1 memory=1Gi\n").unwrap_err().line, 2);
    assert_eq!(parse_inventory("\na state=ready cpu=1 memory=1GB\n").unwrap_err().line, 2);
    assert_eq!(parse_inventory("a state=ready cpu=1 memory=1Gi used_memory=-1\n").unwrap_err().line, 1);
}
