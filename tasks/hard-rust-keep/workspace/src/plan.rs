//! The retention planner. docs/RETENTION.md, section "Rules", describes the
//! behavior.

use std::fmt;

use crate::input::{Policy, Snapshot};

/// Why a snapshot is kept. The order of the variants is the order of R11.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Reason {
    Last,
    Hourly,
    Daily,
    Weekly,
    Monthly,
    Yearly,
    Within,
    WithinDaily,
    Tag,
    Safety,
}

impl Reason {
    /// The name in the output: "last", ..., "within-daily", "tag", "safety".
    pub fn name(self) -> &'static str {
        match self {
            Reason::Last => "last",
            Reason::Hourly => "hourly",
            Reason::Daily => "daily",
            Reason::Weekly => "weekly",
            Reason::Monthly => "monthly",
            Reason::Yearly => "yearly",
            Reason::Within => "within",
            Reason::WithinDaily => "within-daily",
            Reason::Tag => "tag",
            Reason::Safety => "safety",
        }
    }
}

/// The decision for one snapshot. `reasons` is empty for a removed snapshot.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub id: String,
    pub keep: bool,
    pub reasons: Vec<Reason>,
}

/// One group (R2). A field is None when it is not in `group-by`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Group {
    pub host: Option<String>,
    pub paths: Option<Vec<String>>,
    pub tags: Option<Vec<String>>,
    /// In the order of R3.
    pub decisions: Vec<Decision>,
}

/// The plan: the groups in the order of R2.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Plan {
    pub groups: Vec<Group>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PlanError {
    /// R1.
    EmptyPolicy,
}

impl fmt::Display for PlanError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PlanError::EmptyPolicy => f.write_str("the policy has no active rule"),
        }
    }
}

impl std::error::Error for PlanError {}

/// Makes the plan (R1 to R11).
pub fn plan(snapshots: &[Snapshot], policy: &Policy) -> Result<Plan, PlanError> {
    let _ = (snapshots, policy);
    todo!("implement the rules of docs/RETENTION.md")
}

/// Gives the text of the plan (R12). `snapshots` are the snapshots that the
/// plan was made from.
pub fn render(plan: &Plan, snapshots: &[Snapshot], policy: &Policy) -> String {
    let _ = (plan, snapshots, policy);
    todo!("implement R12 of docs/RETENTION.md")
}
