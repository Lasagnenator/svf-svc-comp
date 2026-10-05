void fill_array(int *ptr, int iterations) {
    // Overflows if iterations > the underlying allocation of ptr
    for(int i = 0; i < iterations; i++) {
        *(ptr + i) = i;
    }
}

int main() {
    int small_array[3];
    
    // Passing a size argument larger than the actual array
    fill_array(small_array, 5); 
    
    return 0;
}