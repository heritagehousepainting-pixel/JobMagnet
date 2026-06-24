# Local Postgres for tests/dev

Run a throwaway Postgres:

    docker run --rm -d --name jm-pg -p 5433:5432 \
      -e POSTGRES_PASSWORD=jm -e POSTGRES_USER=jm -e POSTGRES_DB=jm postgres:16

Then:

    export DATABASE_URL="postgresql://jm:jm@localhost:5433/jm"
    export TEST_DATABASE_URL="postgresql://jm:jm@localhost:5433/jm"

The test suites create and drop their own throwaway database off TEST_DATABASE_URL,
so they never touch the base database.
