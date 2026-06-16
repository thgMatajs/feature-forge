package com.example;

import com.example.domain.User;
import com.example.repository.AuthRepository;
import java.util.List;

public class LoginUseCase {
    private final AuthRepository authRepo;

    public LoginUseCase(AuthRepository authRepo) {
        this.authRepo = authRepo;
    }

    public User execute(String email, String password) {
        return authRepo.login(email, password);
    }
}
