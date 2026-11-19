//! `keepr`: decides which backup snapshots to keep (docs/RETENTION.md).

pub mod input;
pub mod plan;
pub mod time;

pub use input::{parse_policy, parse_snapshots, parse_span, GroupBy, InputError, Policy, Snapshot, Span};
pub use plan::{plan, render, Decision, Group, Plan, PlanError, Reason};
pub use time::{Offset, Timestamp};
