#import "UserModel.h"
#import "../Services/AuthService.h"
@import Foundation;

@interface UserModel ()
@property (nonatomic, strong) NSString *internalToken;
@end

@implementation UserModel

- (instancetype)initWithId:(NSString *)userId name:(NSString *)name {
    self = [super init];
    if (self) {
        _userId = userId;
        _name = name;
    }
    return self;
}

- (NSString *)displayName {
    return [NSString stringWithFormat:@"%@ (%@)", self.name, self.userId];
}

+ (instancetype)anonymousUser {
    return [[self alloc] initWithId:@"0" name:@"Guest"];
}
@end
