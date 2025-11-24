void reach_error() {}

void f(int x) {
    if (x == 0) {
        reach_error();
    }
}

int main() {
    f(0);
}
