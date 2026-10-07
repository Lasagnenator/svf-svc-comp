int main(int argc, char **argv) {
    int arr[5];
    int index = 0;
    
    if (argc > 3) {
        index = 10; // Out of bounds index
    } else {
        index = 3;  // Safe index
    }
    
    // The analysis engine must evaluate the branches to flag this
    arr[index] = 42; 
    
    return 0;
}