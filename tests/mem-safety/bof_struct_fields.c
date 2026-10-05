struct BufferPair {
    char buf1[8];
    int secret_flag;
    char buf2[8];
};

int main() {
    struct BufferPair bp;
    bp.secret_flag = 0;
    
    // Writes out of bounds of buf1, overwriting secret_flag
    for(int i = 0; i < 12; i++) {
        bp.buf1[i] = 'A';
    }
    
    return 0;
}