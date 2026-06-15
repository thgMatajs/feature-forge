package com.example.service;

import com.example.di.Inject;
import com.example.di.Singleton;

@Singleton
public class InjectService {
    @Inject
    public InjectService() {}

    public String greet(String name) {
        return "Hello, " + name;
    }
}
