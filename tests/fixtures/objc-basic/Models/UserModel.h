#import <Foundation/Foundation.h>

@interface UserModel : NSObject
@property (nonatomic, strong) NSString *userId;
@property (nonatomic, strong) NSString *name;
- (instancetype)initWithId:(NSString *)userId name:(NSString *)name;
- (NSString *)displayName;
@end
