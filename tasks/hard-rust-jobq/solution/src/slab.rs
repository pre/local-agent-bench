//! A slab: values in a vector, addressed by generational keys.
//!
//! A key has the index of a slot and the generation of the slot. When a value
//! is removed, its slot goes to the free list, and a later insert can use the
//! slot again. The generation tells the old key and the new key apart.

use std::ops::{Index, IndexMut};

/// The address of a value in a [`Slab`].
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Key {
    index: u32,
    gen: u32,
}

impl Key {
    /// The index of the slot.
    pub fn index(self) -> usize {
        self.index as usize
    }

    /// The generation of the slot when the key was made.
    pub fn generation(self) -> u32 {
        self.gen
    }
}

#[derive(Debug)]
struct Slot<T> {
    gen: u32,
    value: Option<T>,
}

/// Values addressed by [`Key`].
#[derive(Debug)]
pub struct Slab<T> {
    slots: Vec<Slot<T>>,
    free: Vec<u32>,
    len: usize,
}

impl<T> Default for Slab<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> Slab<T> {
    pub fn new() -> Self {
        Slab { slots: Vec::new(), free: Vec::new(), len: 0 }
    }

    /// The number of values.
    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Adds a value and gives its key. The slot of the most recent removal is
    /// used first.
    pub fn insert(&mut self, value: T) -> Key {
        self.len += 1;
        if let Some(index) = self.free.pop() {
            let slot = &mut self.slots[index as usize];
            debug_assert!(slot.value.is_none());
            slot.value = Some(value);
            return Key { index, gen: slot.gen };
        }
        let index = u32::try_from(self.slots.len()).expect("too many slots");
        self.slots.push(Slot { gen: 0, value: Some(value) });
        Key { index, gen: 0 }
    }

    /// The value of the key, or None if the value was removed.
    pub fn get(&self, key: Key) -> Option<&T> {
        let slot = self.slots.get(key.index())?;
        if slot.gen != key.gen {
            return None;
        }
        slot.value.as_ref()
    }

    pub fn get_mut(&mut self, key: Key) -> Option<&mut T> {
        let slot = self.slots.get_mut(key.index())?;
        if slot.gen != key.gen {
            return None;
        }
        slot.value.as_mut()
    }

    pub fn contains(&self, key: Key) -> bool {
        self.get(key).is_some()
    }

    /// Removes the value of the key and gives it. Gives None if the key is
    /// not valid (also when its value was already removed).
    pub fn remove(&mut self, key: Key) -> Option<T> {
        let slot = self.slots.get_mut(key.index())?;
        if slot.gen != key.gen {
            return None;
        }
        let value = slot.value.take()?;
        slot.gen = slot.gen.wrapping_add(1);
        self.free.push(key.index);
        self.len -= 1;
        Some(value)
    }

    /// The keys and values, in the order of the slots.
    pub fn iter(&self) -> impl Iterator<Item = (Key, &T)> {
        self.slots.iter().enumerate().filter_map(|(i, s)| {
            s.value.as_ref().map(|v| (Key { index: i as u32, gen: s.gen }, v))
        })
    }
}

impl<T> Index<Key> for Slab<T> {
    type Output = T;

    fn index(&self, key: Key) -> &T {
        self.get(key).expect("invalid slab key")
    }
}

impl<T> IndexMut<Key> for Slab<T> {
    fn index_mut(&mut self, key: Key) -> &mut T {
        self.get_mut(key).expect("invalid slab key")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn insert_get_remove() {
        let mut s = Slab::new();
        let a = s.insert("a");
        let b = s.insert("b");
        assert_eq!(s.len(), 2);
        assert_eq!(s[a], "a");
        assert_eq!(s.remove(a), Some("a"));
        assert_eq!(s.get(a), None);
        assert_eq!(s.remove(a), None);
        assert_eq!(s[b], "b");
        assert_eq!(s.len(), 1);
    }

    #[test]
    fn reuses_free_slots() {
        let mut s = Slab::new();
        let a = s.insert(1);
        s.insert(2);
        s.remove(a);
        let c = s.insert(3);
        assert_eq!(c.index(), a.index());
        assert_eq!(s.len(), 2);
        assert_eq!(s.iter().map(|(_, v)| *v).collect::<Vec<_>>(), vec![3, 2]);
    }
}
