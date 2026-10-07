int main() {
    int matrix[2][3];
    
    // Valid indices are matrix[0][0] to matrix[1][2]
    
    // Row overflow: Accessing row 2 (out of bounds)
    matrix[2][0] = 99;
    
    // Column overflow: Accessing column 3, which leaks into the next row in memory
    matrix[0][3] = 42; 
    
    return 0;
}