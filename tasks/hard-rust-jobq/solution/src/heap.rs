//! The run queue: a binary min-heap of entries, ordered by due time and then
//! by sequence number. The heap knows the position of each entry, so it can
//! remove or change any entry in O(log n).

use crate::slab::Key;

const ABSENT: usize = usize::MAX;

/// One scheduled job in the queue.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Entry {
    pub due: u64,
    pub seq: u64,
    pub key: Key,
}

impl Entry {
    fn before(&self, other: &Entry) -> bool {
        (self.due, self.seq) < (other.due, other.seq)
    }
}

/// A min-heap of entries with at most one entry for each slab index.
#[derive(Debug, Default)]
pub struct Heap {
    items: Vec<Entry>,
    /// Position in `items` for each slab index, or ABSENT.
    pos: Vec<usize>,
}

impl Heap {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// The first entry: the smallest due time, then the smallest sequence
    /// number.
    pub fn peek(&self) -> Option<&Entry> {
        self.items.first()
    }

    pub fn push(&mut self, entry: Entry) {
        let index = entry.key.index();
        if self.pos.len() <= index {
            self.pos.resize(index + 1, ABSENT);
        }
        assert_eq!(self.pos[index], ABSENT, "slot {index} is already in the heap");
        self.items.push(entry);
        let i = self.items.len() - 1;
        self.pos[index] = i;
        self.sift_up(i);
    }

    pub fn pop(&mut self) -> Option<Entry> {
        let key = self.items.first()?.key;
        self.remove(key)
    }

    /// The position of the entry of the key, if the key is in the heap.
    fn position(&self, key: Key) -> Option<usize> {
        let i = *self.pos.get(key.index())?;
        if i == ABSENT || self.items[i].key != key {
            return None;
        }
        Some(i)
    }

    pub fn contains(&self, key: Key) -> bool {
        self.position(key).is_some()
    }

    /// The sequence number of the entry of the key.
    pub fn seq_of(&self, key: Key) -> Option<u64> {
        self.position(key).map(|i| self.items[i].seq)
    }

    /// Removes the entry of the key and gives it.
    pub fn remove(&mut self, key: Key) -> Option<Entry> {
        let i = self.position(key)?;
        let last = self.items.len() - 1;
        self.swap(i, last);
        let entry = self.items.pop()?;
        self.pos[key.index()] = ABSENT;
        if i < self.items.len() {
            let i = self.sift_up(i);
            self.sift_down(i);
        }
        Some(entry)
    }

    /// Changes the due time and the sequence number of the entry of the key.
    /// Gives false if the key is not in the heap.
    pub fn update(&mut self, key: Key, due: u64, seq: u64) -> bool {
        let Some(i) = self.position(key) else {
            return false;
        };
        self.items[i].due = due;
        self.items[i].seq = seq;
        let i = self.sift_up(i);
        self.sift_down(i);
        true
    }

    /// Moves the entry at i up to its place. Gives its new position.
    fn sift_up(&mut self, mut i: usize) -> usize {
        while i > 0 {
            let parent = (i - 1) / 2;
            if !self.items[i].before(&self.items[parent]) {
                break;
            }
            self.swap(i, parent);
            i = parent;
        }
        i
    }

    /// Moves the entry at i down to its place. Gives its new position.
    fn sift_down(&mut self, mut i: usize) -> usize {
        loop {
            let left = 2 * i + 1;
            let right = left + 1;
            let mut smallest = i;
            if left < self.items.len() && self.items[left].before(&self.items[smallest]) {
                smallest = left;
            }
            if right < self.items.len() && self.items[right].before(&self.items[smallest]) {
                smallest = right;
            }
            if smallest == i {
                return i;
            }
            self.swap(i, smallest);
            i = smallest;
        }
    }

    fn swap(&mut self, i: usize, j: usize) {
        self.items.swap(i, j);
        self.pos[self.items[i].key.index()] = i;
        self.pos[self.items[j].key.index()] = j;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::slab::Slab;

    fn entries(n: usize) -> (Slab<()>, Vec<Key>) {
        let mut slab = Slab::new();
        let keys = (0..n).map(|_| slab.insert(())).collect();
        (slab, keys)
    }

    #[test]
    fn pops_in_order() {
        let (_, keys) = entries(6);
        let mut h = Heap::new();
        let dues = [50, 10, 40, 10, 30, 20];
        for (i, k) in keys.iter().enumerate() {
            h.push(Entry { due: dues[i], seq: i as u64, key: *k });
        }
        let order: Vec<(u64, u64)> = std::iter::from_fn(|| h.pop()).map(|e| (e.due, e.seq)).collect();
        assert_eq!(order, vec![(10, 1), (10, 3), (20, 5), (30, 4), (40, 2), (50, 0)]);
    }

    #[test]
    fn remove_first_and_last() {
        let (_, keys) = entries(4);
        let mut h = Heap::new();
        for (i, k) in keys.iter().enumerate() {
            h.push(Entry { due: 10 * (i as u64 + 1), seq: i as u64, key: *k });
        }
        assert_eq!(h.remove(keys[0]).map(|e| e.due), Some(10));
        assert_eq!(h.remove(keys[3]).map(|e| e.due), Some(40));
        assert_eq!(h.remove(keys[3]), None);
        assert_eq!(h.pop().map(|e| e.due), Some(20));
        assert_eq!(h.pop().map(|e| e.due), Some(30));
        assert!(h.is_empty());
    }

    #[test]
    fn update_moves_entry() {
        let (_, keys) = entries(3);
        let mut h = Heap::new();
        for (i, k) in keys.iter().enumerate() {
            h.push(Entry { due: 10 * (i as u64 + 1), seq: i as u64, key: *k });
        }
        assert!(h.update(keys[2], 5, 3));
        assert_eq!(h.peek().map(|e| e.key), Some(keys[2]));
        assert!(h.update(keys[2], 100, 4));
        assert_eq!(h.pop().map(|e| e.key), Some(keys[0]));
    }
}
