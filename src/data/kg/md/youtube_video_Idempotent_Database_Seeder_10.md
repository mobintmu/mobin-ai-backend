# Idempotent Database Seeder

**Type:** YouTube Video

This technical guide describes the creation of an idempotent database seeder for a Go-based web service built on Clean Architecture. The system is designed to separate structural schema changes from initial data population, ensuring that migrations remain clean and versioned. By using a tracking table called seed_history, the application can automatically inject data on startup without creating duplicate records. The implementation utilizes Uber FX for dependency injection, ensuring that seeds are executed in a specific order immediately after migrations. Safety is further maintained through transactional integrity and conditional SQL logic, which prevents errors during re-runs or environment-specific deployments. Ultimately, this approach allows developers to add new data by simply creating numbered SQL files without modifying the core application logic.
