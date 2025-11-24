void reach_error() {}

void rec(int x) {
    if (x == 0) reach_error();
    else rec(x - 1);
}

int main() {
    rec(3);
}
