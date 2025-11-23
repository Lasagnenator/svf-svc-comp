void reach_error() {}

int main() {
    int x = 3;

    if (x > 10) {
        reach_error();  // 永远不会执行
    }

    return 0;
}
