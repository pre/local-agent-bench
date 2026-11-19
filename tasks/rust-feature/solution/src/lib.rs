//! Selects a node for a batch job.
//!
//! The `placer` command reads a node inventory (see
//! [`parse_inventory`]) and prints the name of the node that [`place`]
//! selects for a job:
//!
//! ```text
//! placer <inventory-file> <cpu> <memory>
//! placer nodes.txt 16 256Gi
//! ```
//!
//! # Placement rules
//!
//! `pub fn place<'a>(nodes: &'a [Node], request: &Request) -> Option<&'a Node>`
//! selects the node for a job that requests `request`:
//!
//! 1. The free CPU of a node is `cpu - used_cpu`, and the free memory is
//!    `memory - used_memory`. A free value is zero when the used value is
//!    larger than the allocatable value.
//! 2. A node is a candidate when its state is [`NodeState::Ready`] and its
//!    free CPU and its free memory are both equal to or larger than the
//!    request.
//! 3. From the candidates, `place` selects the node with the least free
//!    memory after the job is placed (best fit). If two or more nodes have
//!    the same value, it selects the one with the least free CPU after the
//!    job is placed. If they are still equal, it selects the node whose
//!    name comes first in byte order.
//! 4. When there is no candidate, `place` returns `None`.

pub mod inventory;
mod place;
pub mod quantity;

pub use inventory::{parse_inventory, InventoryError, Node, NodeState, Request};
pub use place::place;
pub use quantity::{Quantity, QuantityError};
