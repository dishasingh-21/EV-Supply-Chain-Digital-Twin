// Binary-heap priority queue, ordered by `.f` (A* score). Same shape as the
// original client-side implementation, unchanged — just relocated.
class PriorityQueue {
  constructor() {
    this.heap = [];
  }
  getLeftChildIndex(i) { return 2 * i + 1; }
  getRightChildIndex(i) { return 2 * i + 2; }
  getParentIndex(i) { return Math.floor((i - 1) / 2); }
  hasLeftChild(i) { return this.getLeftChildIndex(i) < this.heap.length; }
  hasRightChild(i) { return this.getRightChildIndex(i) < this.heap.length; }
  hasParent(i) { return this.getParentIndex(i) >= 0; }
  leftChild(i) { return this.heap[this.getLeftChildIndex(i)]; }
  rightChild(i) { return this.heap[this.getRightChildIndex(i)]; }
  parent(i) { return this.heap[this.getParentIndex(i)]; }
  swap(i, j) { [this.heap[i], this.heap[j]] = [this.heap[j], this.heap[i]]; }
  isEmpty() { return this.heap.length === 0; }
  top() { return this.heap.length ? this.heap[0] : null; }

  remove() {
    if (this.heap.length === 0) return null;
    const item = this.heap[0];
    this.heap[0] = this.heap[this.heap.length - 1];
    this.heap.pop();
    this.heapifyDown();
    return item;
  }

  add(item) {
    this.heap.push(item);
    this.heapifyUp();
  }

  heapifyUp() {
    let index = this.heap.length - 1;
    while (this.hasParent(index) && this.parent(index).f > this.heap[index].f) {
      this.swap(this.getParentIndex(index), index);
      index = this.getParentIndex(index);
    }
  }

  heapifyDown() {
    let index = 0;
    while (this.hasLeftChild(index)) {
      let smaller = this.getLeftChildIndex(index);
      if (this.hasRightChild(index) && this.rightChild(index).f < this.leftChild(index).f) {
        smaller = this.getRightChildIndex(index);
      }
      if (this.heap[index].f > this.heap[smaller].f) {
        this.swap(smaller, index);
        index = smaller;
      } else {
        break;
      }
    }
  }
}

module.exports = { PriorityQueue };
